"""M6 编排：四账、影响面、导出内容。"""
from __future__ import annotations

from ... import errors
from ..m4_graph import builder
from ..m5_versions import intervals
from . import export_out, impact, json_out


def accounts(*, summary: dict, metrics: list[dict], nodes: list[dict],
             edges: list[dict], components: list[dict], isolated_lines: int,
             reports: list[dict]) -> dict:
    """四账：行、节点、边、分量。每一项都由独立的数据源算出来。"""
    registered = len(metrics)
    blank = summary.get("blank", 0)
    comment = summary.get("comment", 0)
    line_terms = [
        {"label": "注册指标行", "value": registered},
        {"label": "隔离行", "value": isolated_lines},
        {"label": "空行", "value": blank},
        {"label": "注释行", "value": comment},
    ]
    line_total = registered + isolated_lines + blank + comment

    kind_counts: dict[str, int] = {}
    for node in nodes:
        kind_counts[node["kind"]] = kind_counts.get(node["kind"], 0) + 1
    node_terms = [
        {"label": "指标", "value": kind_counts.get(builder.METRIC, 0)},
        {"label": "字段", "value": kind_counts.get(builder.FIELD, 0)},
        {"label": "维度", "value": kind_counts.get(builder.DIM, 0)},
        {"label": "报表", "value": kind_counts.get(builder.REPORT, 0)},
    ]
    node_total = sum(term["value"] for term in node_terms)

    edge_counts: dict[str, int] = {}
    for edge in edges:
        edge_counts[edge["kind"]] = edge_counts.get(edge["kind"], 0) + 1
    edge_terms = [
        {"label": builder.EDGE_LABELS["metric_metric"],
         "value": edge_counts.get("metric_metric", 0)},
        {"label": builder.EDGE_LABELS["metric_field"],
         "value": edge_counts.get("metric_field", 0)},
        {"label": builder.EDGE_LABELS["metric_dim"],
         "value": edge_counts.get("metric_dim", 0)},
        {"label": builder.EDGE_LABELS["report_metric"],
         "value": edge_counts.get("report_metric", 0)},
    ]
    edge_total = sum(term["value"] for term in edge_terms)

    cycle_metrics = sum(c["size"] for c in components if c["is_cycle"])
    acyclic_metrics = sum(c["size"] for c in components if not c["is_cycle"])
    comp_terms = [
        {"label": "环内指标", "value": cycle_metrics},
        {"label": "非环指标", "value": acyclic_metrics},
    ]
    comp_total = cycle_metrics + acyclic_metrics

    rows = []
    for name, total, terms in (
        ("行账", line_total, line_terms),
        ("节点账", node_total, node_terms),
        ("边账", edge_total, edge_terms),
        ("分量账", comp_total, comp_terms),
    ):
        rows.append({"account": name, "total": total, "terms": terms,
                     "balanced": total == sum(t["value"] for t in terms)})

    resolved_reports = [r for r in reports if r["resolved"]]
    return {
        "accounts": rows,
        "all_balanced": all(row["balanced"] for row in rows),
        "details": {
            "lines_total": summary.get("total", 0),
            "lines_registered": registered,
            "lines_isolated": isolated_lines,
            "nodes_total": len(nodes),
            "edges_total": len(edges),
            "reports_total": len(reports),
            "reports_resolved": len(resolved_reports),
            "cycle_components": sum(1 for c in components if c["is_cycle"]),
        },
    }


def totals_payload(accounts_result: dict) -> dict:
    details = accounts_result["details"]
    return {
        "lines_total": str(details["lines_total"]),
        "metrics_registered": str(details["lines_registered"]),
        "lines_isolated": str(details["lines_isolated"]),
        "nodes_total": str(details["nodes_total"]),
        "edges_total": str(details["edges_total"]),
        "reports_total": str(details["reports_total"]),
        "cycle_count": str(details["cycle_components"]),
        "accounts_json": json_out.dumps(accounts_result),
    }


def impact_view(store, batch_id: str, metric: str | None) -> dict:
    metrics = store.load_metrics(batch_id)
    edges = store.load_edges(batch_id)
    reports = store.load_reports(batch_id)
    if not metrics:
        raise errors.NotFound("该批次没有注册指标", code="X_EMPTY_SELECTION")
    names = [m["name"] for m in metrics]
    target = metric or names[0]
    if target not in names:
        raise errors.NotFound(f"指标未注册：{target}", code="G_REF_UNKNOWN")
    payload = impact.compute(target, metrics=metrics, edges=edges, reports=reports)
    payload["ranking"] = impact.rank_all(metrics, edges, reports)[:12]
    payload["names"] = names
    return payload


def reconcile_view(store, batch_id: str) -> dict:
    totals = store.load_totals(batch_id)
    if "accounts_json" not in totals:
        raise errors.NotFound("该批次没有账目结果", code="X_EMPTY_SELECTION")
    return json_out.loads(totals["accounts_json"])


def export_bundle(store, batch_id: str) -> dict:
    batch = store.get_batch(batch_id)
    manifest = store.load_manifest(batch_id) or {}
    metrics = store.load_metrics(batch_id)
    return {
        "metrics_csv": export_out.metrics_csv(metrics),
        "edges_csv": export_out.edges_csv(store.load_edges(batch_id)),
        "conflicts_csv": export_out.conflicts_csv(store.load_conflicts(batch_id)),
        "manifest_json": json_out.dumps(json_out.manifest_payload(batch, manifest)),
        "diagnostics_count": len(store.load_diagnostics(batch_id)),
    }


def version_window_note(rows: list[dict]) -> dict:
    overlap = [r for r in rows if r["status"] == "OVERLAP"]
    return {"overlap_rows": len(overlap),
            "window": "[valid_from, valid_to)",
            "label": intervals.status_label("OVERLAP")}
