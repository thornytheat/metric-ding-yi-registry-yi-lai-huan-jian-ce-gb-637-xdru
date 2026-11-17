"""M7 纯规则：同名指标的版本含义、替代等级、目标解析。

同名指标在不同 BI 里可能同时有两个版本生效，下线前要先说清「下的是哪一版」。
这里用固定台账行钉死三态：生效一个、多版并存、没有生效版本。
"""
from __future__ import annotations

import datetime as dt

from app.modules.m7_retire import plan

EVAL_DAY = dt.date(2026, 11, 15)


def version_row(version, start, end, status="OK"):
    return {"metric": "销售额", "version": version, "valid_from": start,
            "valid_to": end, "status": status}


def metric(name, *, expr="SUM(order_amt)", aggs=("SUM",), fields=("order_amt",),
           where=None, group=("store_id",), depends=()):
    return {"name": name, "aggregators": list(aggs), "fields": list(fields),
            "expr_text": expr, "where": where, "group_by": list(group),
            "depends_declared": list(depends)}


def test_half_open_interval_boundary_excludes_valid_to():
    row = version_row(1, "2026-01-01", "2026-11-15")
    assert plan.covers(row, dt.date(2026, 11, 14)) is True
    assert plan.covers(row, dt.date(2026, 11, 15)) is False
    assert plan.covers(row, dt.date(2026, 1, 1)) is True
    assert plan.covers(row, dt.date(2025, 12, 31)) is False


def test_version_state_picks_only_effective_one():
    rows = [version_row(1, "2026-01-01", "2026-04-01"),
            version_row(2, "2026-07-01", "9999-12-31")]
    state = plan.version_state("销售额", rows, EVAL_DAY)
    assert state["total"] == 2
    assert state["effective"] == 1
    assert state["versions"] == [2]
    assert state["state"] == "ok"
    assert state["label"] == "生效"


def test_version_state_flags_two_effective_versions():
    rows = [version_row(1, "2026-01-01", "2027-01-01"),
            version_row(2, "2026-06-01", "9999-12-31")]
    state = plan.version_state("销售额", rows, EVAL_DAY)
    assert state["effective"] == 2
    assert state["state"] == "ambiguous"
    assert state["versions"] == [1, 2]


def test_version_state_missing_when_inverted_or_expired():
    rows = [version_row(1, "2026-02-01", "2026-05-01"),
            version_row(2, "2026-05-01", "2026-02-01", status="INVERTED")]
    state = plan.version_state("销售额", rows, EVAL_DAY)
    assert state["effective"] == 0
    assert state["state"] == "missing"
    assert state["flags"] == ["INVERTED"]
    assert state["label"] == "无生效版本"


def test_version_state_of_unknown_metric_is_empty():
    state = plan.version_state("没登记", [version_row(1, "2026-01-01", "9999-12-31")],
                               EVAL_DAY)
    assert state["total"] == 0
    assert state["state"] == "missing"


def test_replacement_levels_exact_partial_and_none():
    metrics = [
        metric("销售额"),
        metric("销售额A"),
        metric("销售额B", group=("store_id", "channel")),
        metric("销售额C", expr="SUM(order_amt)-SUM(refund_amt)",
               fields=("order_amt", "refund_amt")),
    ]
    exact = plan.replacement("销售额", metrics)
    assert exact["level"] == "exact"
    assert exact["exact"] == ["销售额A"]
    assert exact["partial"] == ["销售额B"]

    partial = plan.replacement("销售额A", metrics)
    assert partial["level"] == "exact"
    assert partial["exact"] == ["销售额"]

    single = plan.replacement("销售额A", [metric("销售额A")])
    assert single["level"] == "none"
    assert single["candidates"] == []

    missing = plan.replacement("没登记", metrics)
    assert missing["level"] == "none"


def test_where_difference_is_not_partial():
    metrics = [metric("销售额", where={"field": "channel", "value": "线上"}),
               metric("门店销售额")]
    result = plan.replacement("销售额", metrics)
    assert result["level"] == "none"


def test_parse_targets_dedups_fullwidth_and_ideographic_commas():
    parsed = plan.parse_targets("销售额，毛利额、销售额 , 客单价")
    assert parsed["targets"] == ["销售额", "毛利额", "客单价"]
    assert parsed["duplicates"] == ["销售额"]
    assert parsed["empty"] is False
    assert plan.parse_targets("  ")["empty"] is True
    assert plan.parse_targets(["销售额", "  "])["targets"] == ["销售额"]


def test_downstream_skips_self_loop_and_target():
    adj = {"自比值": ["自比值"], "销售额": [], "毛利率": ["销售额"]}
    reverse = plan.reverse_adjacency(adj)
    assert plan.downstream(["销售额"], reverse) == ["毛利率"]
    assert plan.downstream(["自比值"], reverse) == []
