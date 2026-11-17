"""M2 语法规则：全角归一、别名、优先级、常量保形、错误码。

对应 TRAP-17（字段改名靠别名表收口）。
"""
from __future__ import annotations

import pytest

from app.modules.m2_syntax import coerce, contract, grammar, service
from fixtures import expected as EX


def test_alias_maps_renamed_field():
    """TRAP-17：老列名 order_amount 与中文别名都映射到登记名。"""
    assert contract.resolve_field("order_amount") == "order_amt"
    assert contract.resolve_field("订单金额") == "order_amt"
    assert contract.resolve_field("ORDER_AMT") == "order_amt"
    assert contract.resolve_field("discount_amt") is None

    parsed = grammar.parse("别名指标 = SUM(order_amount) - SUM(退款金额)")
    fields: list[str] = []
    grammar.walk(parsed["expr"], fields=fields, metrics=[], aggs=[])
    assert fields == ["order_amt", "refund_amt"]


def test_fullwidth_punctuation_normalized():
    """全角括号、全角逗号、全角减号归一后与半角等价。"""
    full = grammar.parse("全角 = SUM（order_amt）－SUM（refund_amt）")
    half = grammar.parse("全角 = SUM(order_amt)-SUM(refund_amt)")
    assert grammar.signature("全角", full) == grammar.signature("全角", half)
    assert coerce.normalize_punct("１，２（３）") == "1,2(3)"

    grouped = grammar.parse("分组 = SUM(order_amt) group by store_id，channel")
    assert grouped["group_by"] == ["store_id", "channel"]


def test_chinese_aggregator_alias():
    parsed = grammar.parse("中文 = 求和(order_amt) - 求和(refund_amt)")
    aggs: list[str] = []
    grammar.walk(parsed["expr"], fields=[], metrics=[], aggs=aggs)
    assert aggs == ["SUM", "SUM"]
    assert grammar.expr_text(parsed["expr"]) == "SUM(order_amt)-SUM(refund_amt)"


def test_precedence_renders_canonical_text():
    parsed = grammar.parse("比 = ref(销售额) / ref(客单价) - 1")
    assert grammar.expr_text(parsed["expr"]) == "ref(销售额)/ref(客单价)-1"
    parens = grammar.parse("括号 = (ref(销售额) + ref(客单价)) / 2")
    assert grammar.expr_text(parens["expr"]) == "(ref(销售额)+ref(客单价))/2"


def test_big_integer_constant_preserved():
    """超过 2^53 的常量按 Decimal 字符串保形，逐字相同。"""
    parsed = grammar.parse(f"大数 = SUM(order_amt) - {EX.BIG_NUMBER}")
    assert EX.BIG_NUMBER in grammar.expr_text(parsed["expr"])


def test_aggregator_arity_rejected():
    with pytest.raises(grammar.ParseError) as multi:
        grammar.parse("多参 = SUM(order_amt, qty)")
    assert multi.value.code == "Q_AGG_ARITY"

    with pytest.raises(grammar.ParseError) as nested:
        grammar.parse("嵌套 = MAX(AVG(order_amt))")
    assert nested.value.code == "Q_PAREN_UNBALANCED"


def test_unknown_aggregator_rejected():
    with pytest.raises(grammar.ParseError) as exc:
        grammar.parse("未知 = total(order_amt)")
    assert exc.value.code == "Q_AGG_UNKNOWN"


def test_clauses_accept_any_order():
    """where / group by / depends 顺序任意，签名一致。"""
    first = grammar.parse("顺序 = SUM(order_amt) where channel = 线上 "
                          "group by store_id depends: 销售额")
    second = grammar.parse("顺序 = SUM(order_amt) depends: 销售额 "
                           "group by store_id where channel = 线上")
    assert grammar.signature("顺序", first) == grammar.signature("顺序", second)


def test_contract_payload_shape():
    payload = service.contract_view(type("S", (), {"rule_version": "metricreg/1.2.0"})())
    assert payload["rule_version"] == "metricreg/1.2.0"
    assert {row["name"] for row in payload["aggregators"]} >= {"SUM", "COUNT_DISTINCT"}
    assert len(payload["fields"]) == len(contract.config.FIELD_REGISTRY)
    assert payload["dimensions"] == list(contract.config.DIMENSIONS)
    assert "Q_SENTINEL_VALUE" in payload["diag_order"]
    assert {row["level"] for row in payload["conflict_levels"]} == {"BLOCK", "REVIEW", "INFO"}
