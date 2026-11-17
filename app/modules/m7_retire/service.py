"""M7 编排：读批次数据与下线请求台账，算出下线计划。

只用已落库的批次数据，不重跑解析，所以同一批次多次查看结果一致；
请求台账是外部输入，读不到时按空台账处理，不让整页失败。
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from ... import errors
from . import plan

REQUEST_FILE = "retire_requests.csv"


def load_requests(settings, request_file: str | None = None) -> list[dict]:
    """读请求台账：编码回退、去空白、空行跳过；文件缺失返回空列表。"""
    path = Path(settings.sample_dir) / (request_file or REQUEST_FILE)
    if not path.exists():
        return []
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_bytes().decode("gb18030", errors="replace")
    rows: list[dict] = []
    for raw in csv.DictReader(io.StringIO(text)):
        metric = (raw.get("metric") or "").strip()
        if not metric:
            continue
        rows.append({
            "metric": metric,
            "reason": (raw.get("reason") or "").strip(),
            "owner": (raw.get("owner") or "").strip() or "—",
            "requested_on": (raw.get("requested_on") or "").strip() or "—",
        })
    return rows


def _metrics_and_graph(store, batch_id: str) -> dict:
    metrics = store.load_metrics(batch_id)
    if not metrics:
        raise errors.NotFound("该批次没有注册指标", code="X_EMPTY_SELECTION")
    return {
        "metrics": metrics,
        "edges": store.load_edges(batch_id),
        "components": store.load_components(batch_id),
        "reports": store.load_reports(batch_id),
        "versions": store.load_versions(batch_id),
    }


def plan_for(store, settings, batch_id: str, *, targets=None,
             strict: bool = False, request_file: str | None = None) -> dict:
    """targets 为空时用请求台账里已注册的指标；strict 下显式目标写错直接 4xx。"""
    data = _metrics_and_graph(store, batch_id)
    requests = load_requests(settings, request_file)
    known = {item["name"] for item in data["metrics"]}
    parsed = plan.parse_targets(targets) if targets is not None else None
    if parsed is not None and parsed["empty"]:
        raise errors.BadRequest("没有指定下线指标", code="R_NO_TARGETS",
                                detail={"hint": "选至少一个已注册指标再算"})
    request_list, _ = plan.request_rows(requests, known)
    if parsed is not None:
        chosen = parsed["targets"]
        if strict:
            unknown = [name for name in chosen if name not in known]
            if unknown:
                raise errors.NotFound(f"下线目标未注册：{', '.join(unknown)}",
                                      code="R_TARGET_UNKNOWN",
                                      detail={"unknown": unknown})
    else:
        chosen = plan.default_targets(request_list, known)
        if not chosen:
            raise errors.NotFound("请求台账里没有可受理的下线指标",
                                  code="R_NO_TARGETS")
    payload = plan.build_plan(
        targets=chosen, metrics=data["metrics"], edges=data["edges"],
        components=data["components"], reports=data["reports"],
        versions=data["versions"], eval_day=settings.eval_date,
        requests=requests)
    payload["batch_id"] = batch_id
    payload["request_file"] = request_file or REQUEST_FILE
    return payload


def page_payload(store, settings, batch_id: str, *, targets=None,
                 request_file: str | None = None) -> dict:
    """页面用：目标写错时不抛错，退回到台账默认目标并留一条提示。"""
    try:
        return plan_for(store, settings, batch_id, targets=targets,
                        strict=True, request_file=request_file)
    except errors.MetricregError as exc:
        payload = plan_for(store, settings, batch_id,
                           request_file=request_file)
        payload["notice"] = f"{exc.code} {exc.message}"
        payload["requested"] = str(targets or "")
        return payload


def empty_payload() -> dict:
    return {
        "targets": [], "unknown_targets": [], "rows": [], "affected": [],
        "affected_count": 0, "order": [], "orderable_count": 0, "stuck": [],
        "checklist": [], "blockers": [], "rings": [], "ring_partition": {},
        "isolated": [], "dangling_reports": [], "requests": [], "diagnostics": [],
        "names": [], "eval_date": "", "batch_id": "",
        "counters": {"targets": 0, "unknown_targets": 0, "affected": 0,
                     "orderable": 0, "blocked": 0, "rings": 0, "naive_rings": 0,
                     "singletons": 0, "isolated": 0, "reports": 0,
                     "weight_sum": "0.00"},
        "rules": {}, "notice": "", "requested": "",
    }


def order_csv(payload: dict) -> str:
    return plan.order_csv(payload)
