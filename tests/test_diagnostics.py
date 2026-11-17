"""M3 解析诊断：多余记号、括号、哨兵、重复行、扫描顺序无关。

对应 TRAP-05（行内记号不齐整行隔离）、TRAP-07（哨兵不是 0）、
TRAP-19（多规则同时命中按固定优先级排序）。
"""
from __future__ import annotations

from app.modules.m1_ingest import reader
from app.modules.m3_diagnostics import metrics, quarantine, rules, service
from fixtures import expected as EX

from conftest import codes


def _inspect(line: str) -> dict:
    return rules.inspect_line(7, line)


def test_trailing_token_isolated():
    """TRAP-05：表达式之后多一个记号，整行隔离而不是截断登记。"""
    result = _inspect("尾部分隔符 = SUM(order_amt),")
    assert result["definition"] is None
    assert codes(result["diagnostics"]) == ["Q_TOKEN_EXTRA"]
    assert result["diagnostics"][0]["line_no"] == 7


def test_unbalanced_paren_isolated():
    """TRAP-05：括号少一个，不带默认补全。"""
    result = _inspect("缺失括号 = SUM(order_amt) - SUM(refund_amt")
    assert result["definition"] is None
    assert codes(result["diagnostics"]) == ["Q_PAREN_UNBALANCED"]

    extra = _inspect("多余括号 = SUM(order_amt))")
    assert "Q_PAREN_UNBALANCED" in codes(extra["diagnostics"])


def test_sentinel_value_isolated():
    """TRAP-07：哨兵出现在字段位置与过滤取值位置都要隔离。"""
    field_case = _inspect("哨兵字段 = SUM(N/A)")
    assert codes(field_case["diagnostics"]) == ["Q_SENTINEL_VALUE"]
    assert field_case["diagnostics"][0]["raw_value"] == "N/A"

    where_case = _inspect("哨兵过滤 = SUM(order_amt) where channel = 未知")
    assert "Q_SENTINEL_VALUE" in codes(where_case["diagnostics"])
    assert where_case["definition"] is None


def test_scan_order_does_not_change_result():
    """TRAP-19：把扫描顺序倒过来，诊断集合与排序完全一致。"""
    line = "bad = SUM(N/A) + SUM(missing_amt) group by region"
    forward = _inspect(line)
    backward = rules.inspect_line(7, line, scans=tuple(reversed(rules.SCANS)))
    assert codes(forward["diagnostics"]) == codes(backward["diagnostics"])
    assert forward["diagnostics"] == backward["diagnostics"]


def test_naive_first_error_only_loses_diagnostics():
    """反例：只取第一条命中（按代码书写顺序）会漏掉另外两条。"""
    line = "bad = SUM(N/A) + SUM(missing_amt) group by region"
    found = codes(_inspect(line)["diagnostics"])
    naive = [found[0]]
    assert len(found) == 3
    assert len(naive) == 1
    assert found == sorted(found, key=lambda code: rules.rank(code))
    assert set(found) == {"Q_SENTINEL_VALUE", "Q_FIELD_UNKNOWN", "Q_GROUP_INVALID"}


def test_duplicate_line_isolated(settings, store, run):
    """完全相同的两行：保留首行，第二行按 Q_DUP_LINE 隔离。"""
    diags = store.load_diagnostics(run["batch"]["batch_id"])
    dup = [d for d in diags if d["code"] == "Q_DUP_LINE"]
    assert len(dup) == 1
    assert dup[0]["line_no"] == 34
    assert "第 6 行" in dup[0]["detail"]

    lines = store.load_lines(run["batch"]["batch_id"])
    isolated = [row for row in lines if row["state"] == "isolated"]
    assert len(isolated) == EX.LINES_ISOLATED


def test_distribution_and_levels(run, store):
    diags = store.load_diagnostics(run["batch"]["batch_id"])
    assert len(diags) == EX.DIAG_TOTAL
    by_level = metrics.by_level(diags)
    assert by_level == {"error": 24, "warn": 7, "info": 0}

    rows = metrics.distribution(diags)
    assert rows[0]["level"] == "error"
    assert sum(row["count"] for row in rows) == EX.DIAG_TOTAL
    assert any(row["code"] == "G_CYCLE" and row["count"] == 2 for row in rows)
    assert rows[0]["level_label"] == "隔离"


def test_quarantine_csv_columns(run, store):
    text = quarantine.to_csv_text(store.load_diagnostics(run["batch"]["batch_id"]))
    head, *body = text.splitlines()
    assert head == "行号,原因码,级别,阶段,指标,字段,原值,结论"
    assert len(body) == EX.DIAG_TOTAL
    assert "Q_TOKEN_EXTRA" in text


def test_empty_expression_and_missing_assign():
    assert codes(_inspect("空表达式 =")["diagnostics"]) == ["Q_EXPR_EMPTY"]
    assert codes(_inspect("没有赋值号 SUM(order_amt)")["diagnostics"]) == ["Q_NO_ASSIGN"]
    assert codes(_inspect("= SUM(order_amt)")["diagnostics"]) == ["Q_NAME_INVALID"]
    result = _inspect("备注 = SUM(order_amt) 每月重跑")
    assert codes(result["diagnostics"]) == ["Q_TOKEN_EXTRA"]
    assert result["diagnostics"][0]["detail"].startswith("多余记号")


def test_view_filters_and_export(run, store):
    diags = store.load_diagnostics(run["batch"]["batch_id"])
    only_error = service.view(diags, level="error")
    assert only_error["filtered"] == 24
    assert all(row["level"] == "error" for row in only_error["rows"])

    only_code = service.view(diags, code="G_CYCLE")
    assert only_code["filtered"] == 2
    assert service.view(diags, level="info")["filtered"] == 0
    assert service.export_csv(diags).startswith("行号,原因码")

    rows, _ = reader.split_lines("a = SUM(order_amt)\n")
    result = service.inspect_lines(rows)
    assert result["lines"][0]["state"] == "registered"
