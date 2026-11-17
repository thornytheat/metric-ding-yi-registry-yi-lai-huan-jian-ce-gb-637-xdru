"""影响面：反向可达（谁依赖我）+ 报表权重合计。

反向遍历带 visited 集合，环不会导致无限递归；影响分 = 下游指标数 × 权重合计，
Decimal 两位，可独立复算。
"""
from __future__ import annotations

from collections import deque
from decimal import Decimal

from ... import config
from ..m4_graph import builder


def reverse_adjacency(edges: list[dict]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for edge in edges:
        if edge["kind"] != "metric_metric":
            continue
        src = edge["src"].split(":", 1)[1]
        dst = edge["dst"].split(":", 1)[1]
        reverse.setdefault(dst, []).append(src)
    for key in reverse:
        reverse[key] = sorted(reverse[key])
    return reverse


def downstream(edges: list[dict], metric: str) -> list[str]:
    reverse = reverse_adjacency(edges)
    visited: set[str] = set()
    queue = deque([metric])
    while queue:
        node = queue.popleft()
        for parent in reverse.get(node, []):
            if parent in visited or parent == metric:
                continue
            visited.add(parent)
            queue.append(parent)
    return sorted(visited)


def compute(metric: str, *, metrics: list[dict], edges: list[dict],
            reports: list[dict]) -> dict:
    names = {m["name"] for m in metrics}
    if metric not in names:
        return {"metric": metric, "known": False, "downstream": [],
                "affected_reports": [], "weight_sum": "0.00",
                "downstream_count": 0, "report_count": 0, "score": "0.00"}
    affected_metrics = [metric] + downstream(edges, metric)
    affected_set = set(affected_metrics)
    hit_reports = [r for r in reports if r["resolved"] and r["metric"] in affected_set]
    weight_sum = sum((r["weight"] for r in hit_reports), Decimal("0"))
    weight_sum = weight_sum.quantize(config.DECIMAL_QUANT)
    down_count = len(affected_set) - 1
    score = (Decimal(down_count) * weight_sum).quantize(config.DECIMAL_QUANT)
    return {
        "metric": metric,
        "known": True,
        "downstream": sorted(affected_set - {metric}),
        "downstream_count": down_count,
        "affected_reports": [
            {"report_id": r["report_id"], "report_name": r["report_name"],
             "weight": str(r["weight"].quantize(config.DECIMAL_QUANT)),
             "metric": r["metric"]}
            for r in sorted(hit_reports, key=lambda r: r["report_id"])
        ],
        "report_count": len(hit_reports),
        "weight_sum": str(weight_sum),
        "score": str(score),
        "node_universe": len(names) + len(builder.EDGE_LABELS),
    }


def rank_all(metrics: list[dict], edges: list[dict], reports: list[dict]) -> list[dict]:
    rows = []
    for item in metrics:
        result = compute(item["name"], metrics=metrics, edges=edges, reports=reports)
        rows.append({"metric": item["name"], "line_no": item["line_no"],
                     "downstream_count": result["downstream_count"],
                     "report_count": result["report_count"],
                     "weight_sum": result["weight_sum"], "score": result["score"]})
    rows.sort(key=lambda r: (-Decimal(r["score"]), r["metric"]))
    return rows
