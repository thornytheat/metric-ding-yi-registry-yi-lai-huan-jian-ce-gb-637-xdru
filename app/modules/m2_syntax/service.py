"""M2 编排：契约视图与单行试解析。"""
from __future__ import annotations

from . import contract, grammar


def contract_view(settings) -> dict:
    return contract.describe(settings)


def preview(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {"ok": False, "code": "Q_EXPR_EMPTY", "message": "这一行为空",
                "signature": "", "terms": [], "fields": [], "metrics": [],
                "aggregators": [], "where": None, "group_by": []}
    try:
        ast = grammar.parse(raw)
    except grammar.ParseError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message,
                "signature": "", "terms": [], "fields": [], "metrics": [],
                "aggregators": [], "where": None, "group_by": []}
    fields: list[str] = []
    metrics: list[str] = []
    aggs: list[str] = []
    grammar.walk(ast["expr"], fields=fields, metrics=metrics, aggs=aggs)
    return {
        "ok": True,
        "code": None,
        "message": "",
        "name": ast["name"],
        "signature": grammar.signature(ast["name"], ast),
        "expr_text": grammar.expr_text(ast["expr"]),
        "fields": sorted(set(fields)),
        "metrics": sorted(set(metrics)),
        "aggregators": sorted(set(aggs)),
        "where": ast["where"],
        "group_by": [contract.resolve_field(d) or d for d in ast["group_by"]],
        "depends_declared": ast["depends_declared"],
    }
