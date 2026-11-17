"""M4 依赖图：同名冲突三级、代表元、双向引用、自引用、环、报表边。

对应 TRAP-14（同名冲突归因）、TRAP-20（自引用）、TRAP-21（双向引用不一致）。
"""
from __future__ import annotations

from app.modules.m4_graph import builder, conflicts, service, tarjan
from fixtures import expected as EX


def test_same_name_conflict_levels(run, store):
    """TRAP-14：同名冲突按差异分三级，全部登记。"""
    rows = store.load_conflicts(run["batch"]["batch_id"])
    assert len(rows) == EX.CONFLICTS
    assert [(r["metric"], r["level"], r["kept_line"], r["other_line"]) for r in rows] == \
        list(EX.CONFLICT_ROWS)
    assert rows[0]["diff"] == ["aggregators", "expr"]
    assert rows[1]["diff"] == ["where"]
    assert rows[2]["diff"] == ["group_by"]


def test_conflict_representative_is_first_line(run, store):
    """代表元规则：保留行号最小的一条，与输入先后无关。"""
    metrics = store.load_metrics(run["batch"]["batch_id"])
    kept = {m["name"]: m["line_no"] for m in metrics}
    assert kept["门店销售额"] == 10
    assert kept["销售额"] == 3
    assert kept["毛利额"] == 4

    reversed_candidates = list(reversed(_candidates()))
    resolved = conflicts.resolve(reversed_candidates)
    assert {m["name"]: m["line_no"] for m in resolved["metrics"]}["门店销售额"] == 10


def _candidates():
    base = {"expr_text": "SUM(order_amt)", "where": None, "group_by": ["store_id"],
            "aggregators": ["SUM"], "depends_declared": [], "fields": ["order_amt"],
            "metrics": [], "signature": "x"}
    return [
        {**base, "name": "门店销售额", "line_no": 10},
        {**base, "name": "门店销售额", "line_no": 31,
         "expr_text": "AVG(order_amt)", "aggregators": ["AVG"]},
    ]


def test_one_sided_declaration_detected(run, store):
    """TRAP-21：声明了没用、用了没声明，两侧各给原因码。"""
    diags = store.load_diagnostics(run["batch"]["batch_id"])
    declared_unused = [d for d in diags if d["code"] == "G_DEP_DECLARED_UNUSED"]
    undeclared = [d for d in diags if d["code"] == "G_DEP_UNDECLARED"]
    assert [d["metric"] for d in declared_unused] == ["声明多余"]
    assert declared_unused[0]["raw_value"] == "销售额"
    assert "未声明引用" in {d["metric"] for d in undeclared}
    assert undeclared[0]["raw_value"]


def test_self_reference_detected(run, store):
    """TRAP-20：ref(自己) 单独判自环，不被当成普通边。"""
    diags = store.load_diagnostics(run["batch"]["batch_id"])
    self_ref = [d for d in diags if d["code"] == "G_SELF_REF"]
    assert len(self_ref) == 1
    assert self_ref[0]["metric"] == "自比值"
    assert self_ref[0]["raw_value"] == "自比值 → 自比值"

    components = store.load_components(run["batch"]["batch_id"])
    singles = [c for c in components if c["size"] == 1 and c["is_cycle"]]
    assert [c["members"] for c in singles] == [["自比值"]]


def test_ref_unknown_reported(run, store):
    diags = store.load_diagnostics(run["batch"]["batch_id"])
    unknown = [d for d in diags if d["code"] == "G_REF_UNKNOWN"]
    assert len(unknown) == 1
    assert unknown[0]["raw_value"] == "已下线指标"
    edges = store.load_edges(run["batch"]["batch_id"])
    assert not any("已下线指标" in edge["dst"] for edge in edges)


def test_cycles_match_expected(run, store):
    components = store.load_components(run["batch"]["batch_id"])
    cycles = [c for c in components if c["is_cycle"]]
    assert len(cycles) == EX.CYCLE_COMPONENTS
    assert sum(c["size"] for c in cycles) == EX.CYCLE_METRICS
    member_sets = {tuple(sorted(c["members"])) for c in cycles}
    assert {tuple(sorted(m)) for m in EX.CYCLE_MEMBER_SETS} == member_sets
    for comp in cycles:
        assert comp["path"][0] == comp["path"][-1]
        assert comp["path"][0] in comp["members"]


def test_edge_kinds_and_counts(run, store):
    edges = store.load_edges(run["batch"]["batch_id"])
    counts: dict[str, int] = {}
    for edge in edges:
        counts[edge["kind"]] = counts.get(edge["kind"], 0) + 1
    assert counts == {"metric_metric": 10, "metric_field": 30,
                      "metric_dim": 18, "report_metric": 9}
    assert len(edges) == EX.EDGES_TOTAL
    nodes = store.load_nodes(run["batch"]["batch_id"])
    kind_counts: dict[str, int] = {}
    for node in nodes:
        kind_counts[node["kind"]] = kind_counts.get(node["kind"], 0) + 1
    assert kind_counts == {"metric": 26, "field": EX.FIELD_NODES,
                           "dim": EX.DIM_NODES, "report": EX.REPORTS_RESOLVED}
    assert len(nodes) == EX.NODES_TOTAL


def test_unresolved_report_excluded(run, store):
    reports = store.load_reports(run["batch"]["batch_id"])
    assert len(reports) == EX.REPORTS_TOTAL
    resolved = [r for r in reports if r["resolved"]]
    assert len(resolved) == EX.REPORTS_RESOLVED
    unresolved = [r for r in reports if not r["resolved"]]
    assert [r["report_id"] for r in unresolved] == ["R-10"]
    assert all(r["metric"] != "已下线指标" for r in resolved)
    view = service.graph_view(store, run["batch"]["batch_id"])
    assert view["counts"]["cycles"] == EX.CYCLE_COMPONENTS
    assert view["by_edge"]["report_metric"] == EX.REPORTS_RESOLVED
    assert view["edge_labels"]["metric_field"] == "指标→字段"


def test_singleton_component_without_self_loop_is_not_cycle():
    """边界：单点分量只有在自环时才是环，无边指标不能算环。"""
    nodes = ["孤立", "自环", "上游"]
    adj = {"孤立": [], "自环": ["自环"], "上游": ["下游"]}
    components = tarjan.strongly_connected(nodes, adj)
    flags = {tuple(comp): tarjan.is_cycle(comp, adj) for comp in components}
    assert flags[("自环",)] is True
    assert flags[("孤立",)] is False
    assert flags[("上游",)] is False
