"""M6 影响面与导出：影响分公式、四账守恒、导出内容、清单。

四账自洽是不变量测试；影响分必须是「下游指标数 × 权重合计」的 Decimal 结果。
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.errors import NotFound
from app.modules.m6_impact import impact, json_out, service
from fixtures import expected as EX


def _load(store, batch_id):
    return {"metrics": store.load_metrics(batch_id),
            "edges": store.load_edges(batch_id),
            "reports": store.load_reports(batch_id)}


def test_four_accounts_balance(batch_id, store):
    """不变量：四账各项与合计相等，差额为 0。"""
    payload = service.reconcile_view(store, batch_id)
    assert payload["all_balanced"] is True
    assert [row["account"] for row in payload["accounts"]] == ["行账", "节点账", "边账", "分量账"]
    for row in payload["accounts"]:
        assert row["balanced"] is True
        assert row["total"] == sum(term["value"] for term in row["terms"])

    line_account = payload["accounts"][0]
    assert line_account["total"] == EX.LINES_TOTAL
    assert dict((t["label"], t["value"]) for t in line_account["terms"]) == {
        "注册指标行": EX.LINES_REGISTERED, "隔离行": EX.LINES_ISOLATED,
        "空行": EX.BLANK_LINES, "注释行": EX.COMMENT_LINES}
    details = payload["details"]
    assert details["nodes_total"] == EX.NODES_TOTAL
    assert details["edges_total"] == EX.EDGES_TOTAL
    assert details["reports_resolved"] == EX.REPORTS_RESOLVED
    assert details["cycle_components"] == EX.CYCLE_COMPONENTS


def test_impact_score_formula(batch_id, store):
    data = _load(store, batch_id)
    result = impact.compute("销售额", **data)
    assert result["known"] is True
    assert result["downstream"] == ["动销率", "周转天数", "库存深度", "未声明引用", "毛利率"]
    assert result["downstream_count"] == 5
    assert result["report_count"] == 2
    assert result["weight_sum"] == "7.50"
    assert result["score"] == "37.50"
    assert Decimal(result["score"]) == Decimal(result["downstream_count"]) * \
        Decimal(result["weight_sum"])
    weights = sum(Decimal(r["weight"]) for r in result["affected_reports"])
    assert weights == Decimal("7.50")


def test_downstream_is_cycle_safe(batch_id, store):
    data = _load(store, batch_id)
    for name in ("动销率", "库存深度", "周转天数", "自比值"):
        result = impact.compute(name, **data)
        assert name not in result["downstream"]
        assert result["downstream_count"] == len(result["downstream"])


def test_impact_unknown_metric(batch_id, store, client_with_run):
    with pytest.raises(NotFound) as exc:
        service.impact_view(store, batch_id, "不存在指标")
    assert exc.value.payload()["error"] == "G_REF_UNKNOWN"
    assert client_with_run.get("/api/impact?metric=不存在指标").status_code == 404
    ranking = client_with_run.get("/api/impact").json()["ranking"]
    assert ranking[0]["metric"] == "销售额"
    assert Decimal(ranking[0]["score"]) >= Decimal(ranking[-1]["score"])


def test_metrics_csv_rows(batch_id, store):
    bundle = service.export_bundle(store, batch_id)
    lines = bundle["metrics_csv"].splitlines()
    assert lines[0] == "行号,指标,表达式,过滤,分组,字段,聚合,声明依赖"
    assert len(lines) - 1 == EX.LINES_REGISTERED
    assert "大数常量" in bundle["metrics_csv"]
    assert EX.BIG_NUMBER in bundle["metrics_csv"]
    edge_lines = bundle["edges_csv"].splitlines()
    assert edge_lines[0] == "类型,起点,终点"
    assert len(edge_lines) - 1 == EX.EDGES_TOTAL
    conflict_lines = bundle["conflicts_csv"].splitlines()
    assert conflict_lines[0] == "指标,等级,保留行,冲突行,差异"
    assert len(conflict_lines) - 1 == EX.CONFLICTS
    assert "阻断" in bundle["conflicts_csv"]


def test_manifest_json_fields(batch_id, store):
    bundle = service.export_bundle(store, batch_id)
    payload = json.loads(bundle["manifest_json"])
    assert payload["batch_id"] == batch_id
    assert payload["manifest"]["run_id"].startswith("MR-")
    assert payload["manifest"]["counters"]["registered"] == EX.LINES_REGISTERED
    assert len(payload["manifest"]["inputs"]) == 3
    assert payload["input_digest"] == payload["batch_key"]
    assert json_out.dumps({"value": Decimal("1.25")}) == '{\n  "value": "1.25"\n}'


def test_version_window_note(batch_id, store):
    rows = store.load_versions(batch_id)
    note = service.version_window_note(rows)
    assert note["overlap_rows"] == EX.VERSION_OVERLAP
    assert note["window"] == "[valid_from, valid_to)"
    assert note["label"] == "区间重叠"


def test_export_endpoints(client_with_run):
    for path, expected in (
        ("/api/export/metrics.csv", "行号,指标"),
        ("/api/export/edges.csv", "类型,起点"),
        ("/api/export/conflicts.csv", "指标,等级"),
        ("/api/export/manifest.json", '"run_id"'),
    ):
        response = client_with_run.get(path)
        assert response.status_code == 200
        text = response.content.decode("utf-8-sig")
        assert expected in text
    reconcile = client_with_run.get("/api/reconcile").json()
    assert reconcile["all_balanced"] is True


def test_downstream_excludes_self_reference():
    """反例：自引用指标的下游不能把自己算进去，否则影响分会翻倍。"""
    edges = [{"src": "metric:自比值", "dst": "metric:自比值", "kind": "metric_metric"},
             {"src": "metric:毛利率", "dst": "metric:销售额", "kind": "metric_metric"}]
    assert impact.downstream(edges, "自比值") == []
    assert impact.downstream(edges, "销售额") == ["毛利率"]


def test_impact_of_unknown_metric_is_zero_not_error(batch_id, store):
    """边界：未注册指标返回 0 分结构，不抛异常。"""
    data = _load(store, batch_id)
    result = impact.compute("没登记", metrics=data["metrics"],
                            edges=data["edges"], reports=data["reports"])
    assert result["known"] is False
    assert result["downstream_count"] == 0
    assert result["score"] == "0.00"
