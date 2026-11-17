"""M4 编排：读报表配置 → 建图 → 汇总环与冲突视图。"""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from . import builder


def parse_reports_text(text: str) -> list[dict]:
    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(text))
    for index, raw in enumerate(reader, start=2):
        report_id = (raw.get("report_id") or "").strip()
        metric = (raw.get("metric") or "").strip()
        if not report_id or not metric:
            continue
        weight_text = (raw.get("weight") or "0").strip()
        try:
            weight = Decimal(weight_text)
        except InvalidOperation:
            weight = Decimal("0")
        rows.append({
            "report_id": report_id,
            "report_name": (raw.get("report_name") or report_id).strip(),
            "metric": metric,
            "weight": weight,
            "line_no": index,
        })
    return rows


def analyse(candidates: list[dict], reports: list[dict]) -> dict:
    return builder.build(candidates, reports)


def graph_view(store, batch_id: str) -> dict:
    nodes = store.load_nodes(batch_id)
    edges = store.load_edges(batch_id)
    components = store.load_components(batch_id)
    conflicts = store.load_conflicts(batch_id)
    by_kind: dict[str, int] = {}
    for node in nodes:
        by_kind[node["kind"]] = by_kind.get(node["kind"], 0) + 1
    by_edge: dict[str, int] = {}
    for edge in edges:
        by_edge[edge["kind"]] = by_edge.get(edge["kind"], 0) + 1
    cycles = [c for c in components if c["is_cycle"]]
    return {
        "nodes": nodes,
        "edges": edges,
        "components": components,
        "cycles": cycles,
        "conflicts": conflicts,
        "counts": {"nodes": len(nodes), "edges": len(edges),
                   "components": len(components), "cycles": len(cycles),
                   "cycle_metrics": sum(c["size"] for c in cycles)},
        "by_kind": by_kind,
        "by_edge": by_edge,
        "edge_labels": builder.EDGE_LABELS,
    }
