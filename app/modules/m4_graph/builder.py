"""依赖图：节点四类（指标/字段/维度/报表），边四类，环由 Tarjan 给出。

朴素实现常见的两处错：
1. 只查单向引用（A→B 有就以为 B→A 也有），漏掉半边，这里双向比对声明与实际；
2. 用递归找环，长链直接爆栈，这里用迭代 Tarjan。
"""
from __future__ import annotations

from ... import reasons
from . import conflicts, tarjan

METRIC = "metric"
FIELD = "field"
DIM = "dim"
REPORT = "report"

EDGE_LABELS = {
    "metric_metric": "指标→指标",
    "metric_field": "指标→字段",
    "metric_dim": "指标→维度",
    "report_metric": "报表→指标",
}


def node_id(kind: str, name: str) -> str:
    return f"{kind}:{name}"


def _rank(code: str) -> int:
    from ... import config
    try:
        return config.DIAG_ORDER.index(code)
    except ValueError:
        return len(config.DIAG_ORDER)


def _diag(code: str, *, line_no: int | None, metric: str | None,
          raw_value: str | None = None, detail: str = "") -> dict:
    reason = reasons.get(code)
    return {"code": code, "level": reason.level, "stage": reason.stage,
            "line_no": line_no, "metric": metric, "field": None,
            "raw_value": raw_value, "detail": detail or reason.title,
            "rank": _rank(code)}


def build(candidates: list[dict], report_rows: list[dict]) -> dict:
    resolved = conflicts.resolve(candidates)
    metrics = resolved["metrics"]
    names = {m["name"] for m in metrics}
    by_name = {m["name"]: m for m in metrics}
    diagnostics: list[dict] = list(resolved["diagnostics"])

    # ---- 依赖边与双向引用核验 ----
    adj: dict[str, list[str]] = {name: [] for name in names}
    edges: list[dict] = []
    for metric in metrics:
        actual = set(metric["metrics"])
        declared = set(metric["depends_declared"])
        for target in sorted(actual):
            if target not in names:
                diagnostics.append(_diag(
                    "G_REF_UNKNOWN", line_no=metric["line_no"], metric=metric["name"],
                    raw_value=target))
                continue
            adj[metric["name"]].append(target)
            edges.append({"src": node_id(METRIC, metric["name"]),
                          "dst": node_id(METRIC, target), "kind": "metric_metric"})
        missing = sorted(actual - declared - {t for t in actual if t not in names}
                         - {metric["name"]})
        if missing:
            diagnostics.append(_diag(
                "G_DEP_UNDECLARED", line_no=metric["line_no"], metric=metric["name"],
                raw_value=",".join(missing),
                detail="表达式引用了 " + ",".join(missing) + " 但没有 depends 声明"))
        unused = sorted(declared - actual)
        if unused:
            diagnostics.append(_diag(
                "G_DEP_DECLARED_UNUSED", line_no=metric["line_no"],
                metric=metric["name"], raw_value=",".join(unused),
                detail="声明了 " + ",".join(unused) + " 但表达式里没有 ref"))

    # ---- 强连通分量与环 ----
    components: list[dict] = []
    for order, comp in enumerate(tarjan.strongly_connected(sorted(names), adj)):
        cyclic = tarjan.is_cycle(comp, adj)
        path = tarjan.cycle_path(comp, adj) if cyclic else []
        components.append({
            "comp_id": order, "size": len(comp), "members": comp,
            "is_cycle": cyclic, "path": path,
        })
        if not cyclic:
            continue
        first_line = min(by_name[name]["line_no"] for name in comp)
        if len(comp) == 1:
            diagnostics.append(_diag(
                "G_SELF_REF", line_no=first_line, metric=comp[0],
                raw_value=" → ".join(path),
                detail="指标直接引用自身"))
        else:
            diagnostics.append(_diag(
                "G_CYCLE", line_no=first_line, metric=comp[0],
                raw_value=" → ".join(path),
                detail=f"环内 {len(comp)} 个指标：" + ",".join(comp)))

    # ---- 节点与其余边 ----
    node_map: dict[str, dict] = {}
    for metric in metrics:
        node_map[node_id(METRIC, metric["name"])] = {
            "node_id": node_id(METRIC, metric["name"]),
            "kind": METRIC, "label": metric["name"]}
    for metric in metrics:
        for field_name in metric["fields"]:
            nid = node_id(FIELD, field_name)
            node_map.setdefault(nid, {"node_id": nid, "kind": FIELD, "label": field_name})
            edges.append({"src": node_id(METRIC, metric["name"]), "dst": nid,
                          "kind": "metric_field"})
        for dim in metric["group_by"]:
            nid = node_id(DIM, dim)
            node_map.setdefault(nid, {"node_id": nid, "kind": DIM, "label": dim})
            edges.append({"src": node_id(METRIC, metric["name"]), "dst": nid,
                          "kind": "metric_dim"})

    reports: list[dict] = []
    for row in report_rows:
        target = row["metric"]
        hit = target in names
        reports.append({**row, "resolved": hit})
        if not hit:
            continue
        nid = node_id(REPORT, row["report_id"])
        node_map.setdefault(nid, {"node_id": nid, "kind": REPORT,
                                  "label": row["report_name"]})
        edges.append({"src": nid, "dst": node_id(METRIC, target),
                      "kind": "report_metric"})

    edges.sort(key=lambda e: (e["kind"], e["src"], e["dst"]))
    nodes = sorted(node_map.values(), key=lambda n: (n["kind"], n["node_id"]))
    diagnostics.sort(key=lambda d: (d["line_no"] or 0, d["rank"], d["code"]))
    return {
        "metrics": metrics,
        "nodes": nodes,
        "edges": edges,
        "components": components,
        "conflicts": resolved["conflicts"],
        "reports": reports,
        "adjacency": adj,
        "diagnostics": diagnostics,
    }
