"""下线评估的纯规则：影响面、替代、版本含义、阻断项、迁移清单。

判定顺序写死，不依赖输入顺序：
- 目标先去空去重再按名称排序，重复输入不改变结论；
- 受影响集合 = 目标 ∪ 反向可达（谁依赖目标），环内成员排除在次序之外；
- 替代分两级：签名完全一致算等价替代；只有分组或过滤不同算近似替代；
- 版本只看评估日当天生效的那些，生效版本超过 1 个即阻断（同名指标版本含义）；
- 阻断项按 级别 → 代码 → 指标 排序，规则书写顺序不影响输出。
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from collections import deque
from decimal import Decimal

from ... import config, reasons
from . import cycles, order

EXACT = "exact"
PARTIAL = "partial"
NONE = "none"

REPLACEMENT_LABELS = {
    EXACT: "等价替代",
    PARTIAL: "近似替代",
    NONE: "无替代",
}
STATE_LABELS = {"blocked": "阻断", "review": "复核", "ok": "可下线"}
REQUEST_LABELS = {"ok": "受理", "duplicate": "重复", "unknown": "未注册"}


def _rank(code: str) -> int:
    try:
        return config.DIAG_ORDER.index(code)
    except ValueError:
        return len(config.DIAG_ORDER)


def _diag(code: str, *, metric: str | None = None, detail: str = "") -> dict:
    reason = reasons.get(code)
    return {"code": code, "level": reason.level, "stage": reason.stage,
            "metric": metric, "detail": detail or reason.title, "rank": _rank(code)}


def parse_targets(text) -> dict:
    """逗号、顿号、全角逗号都能分开；空串与重复项折掉。"""
    if isinstance(text, (list, tuple)):
        raw = ",".join(str(item) for item in text)
    else:
        raw = str(text or "")
    normalized = raw.replace("，", ",").replace("、", ",")
    ordered: list[str] = []
    duplicates: list[str] = []
    for part in normalized.split(","):
        name = part.strip()
        if not name:
            continue
        if name in ordered:
            duplicates.append(name)
            continue
        ordered.append(name)
    return {"targets": ordered, "duplicates": duplicates, "empty": not ordered}


def reverse_adjacency(adj: dict[str, list[str]]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for src, targets in adj.items():
        for dst in targets:
            if dst == src:
                continue
            reverse.setdefault(dst, []).append(src)
    for key in reverse:
        reverse[key] = sorted(set(reverse[key]))
    return reverse


def downstream(targets: list[str], reverse: dict[str, list[str]]) -> list[str]:
    """谁依赖目标（传递闭包），不含目标自身；自环不会把自己算进来。"""
    roots = set(targets)
    seen: set[str] = set()
    queue: deque[str] = deque(sorted(roots))
    while queue:
        node = queue.popleft()
        for parent in reverse.get(node, []):
            if parent in seen or parent in roots:
                continue
            seen.add(parent)
            queue.append(parent)
    return sorted(seen)


def replacement(metric: str, metrics: list[dict]) -> dict:
    """等价替代要求签名一致；近似替代只差分组或过滤。"""
    by_name = {item["name"]: item for item in metrics}
    shape = by_name.get(metric)
    if shape is None:
        return {"level": NONE, "label": REPLACEMENT_LABELS[NONE],
                "exact": [], "partial": [], "candidates": []}
    exact: list[str] = []
    partial: list[str] = []
    for other in sorted(metrics, key=lambda item: item["name"]):
        if other["name"] == metric:
            continue
        same_shape = (
            sorted(other["aggregators"]) == sorted(shape["aggregators"])
            and sorted(other["fields"]) == sorted(shape["fields"])
            and other["expr_text"] == shape["expr_text"]
            and (other["where"] or None) == (shape["where"] or None)
        )
        if not same_shape:
            continue
        same_group = sorted(other["group_by"] or []) == sorted(shape["group_by"] or [])
        same_depends = (sorted(other["depends_declared"])
                        == sorted(shape["depends_declared"]))
        if same_group and same_depends:
            exact.append(other["name"])
        else:
            partial.append(other["name"])
    level = EXACT if exact else (PARTIAL if partial else NONE)
    return {"level": level, "label": REPLACEMENT_LABELS[level],
            "exact": exact, "partial": partial,
            "candidates": exact + partial}


def covers(row: dict, day: dt.date) -> bool:
    start = dt.date.fromisoformat(row["valid_from"])
    end = dt.date.fromisoformat(row["valid_to"])
    return start <= day < end


def version_state(metric: str, versions: list[dict], eval_day: dt.date) -> dict:
    """同名指标在评估日生效的版本；0 个与多个都要显式写出来。"""
    mine = [row for row in versions if row["metric"] == metric]
    effective = [row for row in mine if row["status"] == "OK" and covers(row, eval_day)]
    flags = sorted({row["status"] for row in mine if row["status"] != "OK"})
    if len(effective) > 1:
        state = "ambiguous"
    elif not effective:
        state = "missing"
    else:
        state = "ok"
    return {
        "total": len(mine),
        "effective": len(effective),
        "versions": [row["version"] for row in effective],
        "flags": flags,
        "state": state,
        "label": {"ok": "生效", "ambiguous": "多版并存", "missing": "无生效版本"}[state],
    }


def _report_index(reports: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    by_metric: dict[str, list[dict]] = {}
    dangling: list[dict] = []
    for row in reports:
        if not row["resolved"]:
            dangling.append(row)
            continue
        by_metric.setdefault(row["metric"], []).append(row)
    return by_metric, dangling


def _weight(rows: list[dict]) -> Decimal:
    total = sum((row["weight"] for row in rows), Decimal("0"))
    return total.quantize(config.DECIMAL_QUANT)


def _target_row(name: str, *, metrics: list[dict],
                reverse: dict[str, list[str]], reports_by_metric: dict[str, list[dict]],
                versions: list[dict], eval_day: dt.date,
                cycle_set: set[str]) -> dict:
    down = downstream([name], reverse)
    reach = set(down) | {name}
    hit_reports: list[dict] = []
    for member in sorted(reach):
        hit_reports.extend(reports_by_metric.get(member, []))
    hit_reports.sort(key=lambda row: row["report_id"])
    weight = _weight(hit_reports)
    replaced = replacement(name, metrics)
    version = version_state(name, versions, eval_day)
    codes: list[str] = []
    if name in cycle_set:
        codes.append("R_CYCLE_BLOCKED")
    if replaced["level"] == NONE and hit_reports:
        codes.append("R_NO_REPLACEMENT")
    if replaced["level"] == PARTIAL:
        codes.append("R_REPLACEMENT_PARTIAL")
    if version["state"] == "ambiguous":
        codes.append("R_VERSION_AMBIGUOUS")
    if version["state"] == "missing":
        codes.append("R_VERSION_NONE")
    levels = [reasons.level_of(code) for code in codes]
    if reasons.ERROR in levels:
        state = "blocked"
    elif reasons.WARN in levels:
        state = "review"
    else:
        state = "ok"
    return {
        "metric": name,
        "line_no": next((item["line_no"] for item in metrics
                         if item["name"] == name), None),
        "downstream": down,
        "downstream_count": len(down),
        "reports": [{"report_id": row["report_id"], "report_name": row["report_name"],
                     "weight": str(row["weight"].quantize(config.DECIMAL_QUANT))}
                    for row in hit_reports],
        "report_count": len(hit_reports),
        "weight_sum": str(weight),
        "replacement": replaced,
        "version": version,
        "codes": codes,
        "state": state,
        "state_label": STATE_LABELS[state],
    }


def request_rows(requests: list[dict], known: set[str]) -> tuple[list[dict], list[dict]]:
    """请求台账：重复只受理首条，未注册指标记一条诊断，不阻断其它指标。"""
    rows: list[dict] = []
    diagnostics: list[dict] = []
    seen: set[str] = set()
    for item in requests:
        name = (item.get("metric") or "").strip()
        if not name:
            continue
        if name in seen:
            rows.append({**item, "metric": name, "status": "duplicate",
                         "status_label": REQUEST_LABELS["duplicate"]})
            diagnostics.append(_diag(
                "R_REQUEST_DUPLICATE", metric=name,
                detail=f"请求台账里 {name} 出现多次，只受理首条"))
            continue
        seen.add(name)
        status = "ok" if name in known else "unknown"
        rows.append({**item, "metric": name, "status": status,
                     "status_label": REQUEST_LABELS[status]})
        if status == "unknown":
            diagnostics.append(_diag(
                "R_TARGET_UNKNOWN", metric=name,
                detail=f"请求台账里的 {name} 未注册，无法排迁移次序"))
    return rows, diagnostics


def default_targets(rows: list[dict], known: set[str]) -> list[str]:
    names: list[str] = []
    for row in rows:
        name = row["metric"]
        if row["status"] == "ok" and name in known and name not in names:
            names.append(name)
    return names


def build_plan(*, targets: list[str], metrics: list[dict], edges: list[dict],
               components: list[dict], reports: list[dict], versions: list[dict],
               eval_day: dt.date, requests: list[dict] | None = None) -> dict:
    names = sorted(item["name"] for item in metrics)
    known = set(names)
    adj: dict[str, list[str]] = {name: [] for name in names}
    for edge in edges:
        if edge["kind"] != "metric_metric":
            continue
        src = edge["src"].split(":", 1)[1]
        dst = edge["dst"].split(":", 1)[1]
        if src in known and dst in known:
            adj[src].append(dst)
    for name in adj:
        adj[name] = sorted(set(adj[name]))
    reverse = reverse_adjacency(adj)

    ordered_targets = sorted(dict.fromkeys(targets))
    diagnostics: list[dict] = []
    unknown = [name for name in ordered_targets if name not in known]
    usable = [name for name in ordered_targets if name in known]
    for name in unknown:
        diagnostics.append(_diag("R_TARGET_UNKNOWN", metric=name,
                                 detail=f"{name} 未注册，先登记或换一个目标"))

    rings = cycles.minimal_rings(components, adj)
    cycle_set = cycles.ring_members(rings)
    isolated = cycles.isolated_nodes(names, adj)

    reports_by_metric, dangling = _report_index(reports)
    for ring in rings:
        diagnostics.append(_diag(
            "R_RING_MERGED", metric=ring["head"],
            detail=f"环 {ring['ring_id']} 覆盖 {ring['size']} 个指标，"
                   f"起点轮转 {ring['rotations']} 次只计一个环"))
    if isolated:
        diagnostics.append(_diag(
            "R_ISOLATED_SKIPPED", metric=isolated[0],
            detail=f"{len(isolated)} 个孤立指标没有依赖边，不进迁移次序"))
    for row in dangling:
        diagnostics.append(_diag(
            "R_REPORT_DANGLING", metric=row["metric"],
            detail=f"{row['report_id']} 仍引用未注册的 {row['metric']}"))

    request_list, request_diags = request_rows(requests or [], known)
    diagnostics.extend(request_diags)

    rows = [_target_row(name, metrics=metrics, reverse=reverse,
                        reports_by_metric=reports_by_metric, versions=versions,
                        eval_day=eval_day, cycle_set=cycle_set)
            for name in usable]

    affected: set[str] = set()
    for row in rows:
        affected.update(row["downstream"])
        affected.add(row["metric"])
    blocked_metrics = sorted(affected & cycle_set)
    ordering = order.retire_order(affected, adj, cycle_set)

    dependents = order.dependents_index(set(ordering["order"]), adj)
    reports_map = {name: [row["report_id"] for row in reports_by_metric.get(name, [])]
                   for name in ordering["order"]}
    checklist = order.step_rows(ordering["order"], dependents=dependents,
                                reports_by_metric=reports_map)

    blockers: list[dict] = []
    for name in blocked_metrics:
        blockers.append({
            "metric": name, "code": "R_CYCLE_BLOCKED",
            "level": reasons.level_of("R_CYCLE_BLOCKED"),
            "label": "环内",
            "detail": f"{name} 在依赖环内，先拆环再排次序",
        })
    for row in rows:
        for code in row["codes"]:
            if code == "R_CYCLE_BLOCKED":
                continue
            blockers.append({
                "metric": row["metric"], "code": code,
                "level": reasons.level_of(code),
                "label": {"R_NO_REPLACEMENT": "无替代",
                          "R_REPLACEMENT_PARTIAL": "近似替代",
                          "R_VERSION_AMBIGUOUS": "多版并存",
                          "R_VERSION_NONE": "无生效版本"}.get(code, code),
                "detail": reasons.get(code).title,
            })
    blockers.sort(key=lambda item: (reasons.LEVEL_ORDER[item["level"]],
                                    item["code"], item["metric"]))
    for item in blockers:
        diagnostics.append(_diag(item["code"], metric=item["metric"],
                                 detail=item["detail"]))

    diagnostics.sort(key=lambda item: (item["rank"], item["metric"] or "", item["code"]))
    hit_reports: dict[str, dict] = {}
    for row in rows:
        for hit in row["reports"]:
            hit_reports.setdefault(hit["report_id"], hit)
    weight_total = _weight([{"weight": Decimal(hit["weight"])}
                            for hit in hit_reports.values()])
    partition = cycles.partition(rings)
    return {
        "targets": usable,
        "unknown_targets": unknown,
        "rows": rows,
        "affected": sorted(affected),
        "affected_count": len(affected),
        "order": ordering["order"],
        "orderable_count": len(ordering["order"]),
        "stuck": ordering["stuck"],
        "checklist": checklist,
        "blockers": blockers,
        "rings": rings,
        "ring_partition": partition,
        "isolated": isolated,
        "dangling_reports": [
            {"report_id": row["report_id"], "report_name": row["report_name"],
             "metric": row["metric"], "weight": str(row["weight"])}
            for row in dangling
        ],
        "requests": request_list,
        "diagnostics": diagnostics,
        "names": names,
        "eval_date": eval_day.isoformat(),
        "counters": {
            "targets": len(usable),
            "unknown_targets": len(unknown),
            "affected": len(affected),
            "orderable": len(ordering["order"]),
            "blocked": len(blocked_metrics),
            "rings": len(rings),
            "naive_rings": order.naive_ring_count(components, adj),
            "singletons": len(order.singleton_components(components)),
            "isolated": len(isolated),
            "reports": len(hit_reports),
            "weight_sum": str(weight_total),
        },
        "rules": {"order": config.RETIRE_ORDER_RULE,
                  "ring": config.RETIRE_RING_RULE},
    }


def _csv_cell(value) -> str:
    """以 = + - @ 开头的文本加前缀，避免被表格软件当公式执行。"""
    text = str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@"} else text


def order_csv(payload: dict) -> str:
    """迁移清单导出：步骤、指标、依赖方、报表。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["step", "metric", "dependents", "dependents_text",
                     "report_count", "report_ids"])
    for row in payload.get("checklist", []):
        writer.writerow([
            row["step"], _csv_cell(row["metric"]), row["dependents"],
            _csv_cell(row["dependents_text"]), row["report_count"],
            _csv_cell(row["reports_text"]),
        ])
    return buffer.getvalue()
