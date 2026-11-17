"""解析诊断：六条独立扫描 + 一个语法解析，按固定优先级排序。

每条扫描只看一行的词法与文本，互不短路；因此把 SCANS 换个顺序，
同一行得到的诊断集合与排序完全一致（TRAP-19：显式优先级，不靠书写顺序）。
"""
from __future__ import annotations

import re

from ... import config, reasons
from ..m2_syntax import coerce, contract, grammar

AGG_CALL_RE = re.compile(
    r"([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*)\s*\(([^()]*)\)")
WHERE_RE = re.compile(r"\bwhere\s+([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)\s*=\s*(\S+)")
GROUP_RE = re.compile(r"\bgroup\s+by\s+([^|]+)")


def rank(code: str) -> int:
    try:
        return config.DIAG_ORDER.index(code)
    except ValueError:
        return len(config.DIAG_ORDER)


def _diag(code: str, ctx: dict, *, field: str | None = None,
          raw_value: str | None = None, detail: str = "") -> dict:
    reason = reasons.get(code)
    return {
        "code": code,
        "level": reason.level,
        "stage": reason.stage,
        "line_no": ctx["line_no"],
        "metric": ctx.get("name"),
        "field": field,
        "raw_value": raw_value,
        "detail": detail or reason.title,
        "rank": rank(code),
    }


def context(line_no: int, raw: str) -> dict:
    norm = coerce.normalize_punct(raw)
    tokens = grammar.tokenize(norm)
    name = None
    for kind, value, _pos in tokens:
        if kind == "ident":
            name = value
        break
    return {
        "line_no": line_no,
        "raw": raw,
        "norm": norm,
        "tokens": tokens,
        "name": name,
        "has_assign": any(t[0] == "op" and t[1] == "=" for t in tokens),
    }


def agg_calls(ctx: dict) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2).strip()) for m in AGG_CALL_RE.finditer(ctx["norm"])]


# ---------------- 六条扫描 ----------------
def scan_assign(ctx: dict) -> list[dict]:
    if not ctx["has_assign"]:
        return [_diag("Q_NO_ASSIGN", ctx, raw_value=ctx["raw"][:60])]
    return []


def scan_name(ctx: dict) -> list[dict]:
    tokens = ctx["tokens"]
    if not tokens:
        return [_diag("Q_EXPR_EMPTY", ctx)]
    head = tokens[0]
    if head[0] != "ident" or not coerce.is_identifier(head[1]):
        return [_diag("Q_NAME_INVALID", ctx, field="name", raw_value=head[1])]
    return []


def scan_parens(ctx: dict) -> list[dict]:
    depth = 0
    for kind, value, _pos in ctx["tokens"]:
        if kind != "op":
            continue
        if value == "(":
            depth += 1
        elif value == ")":
            depth -= 1
            if depth < 0:
                return [_diag("Q_PAREN_UNBALANCED", ctx, raw_value=")",
                              detail="右括号多于左括号")]
    if depth != 0:
        return [_diag("Q_PAREN_UNBALANCED", ctx, raw_value="(",
                      detail=f"左括号未闭合，缺口 {depth} 个")]
    return []


def scan_nested_agg(ctx: dict) -> list[dict]:
    depth = 0
    tokens = ctx["tokens"]
    for index, (kind, value, _pos) in enumerate(tokens):
        if kind == "op" and value == "(":
            depth += 1
            continue
        if kind == "op" and value == ")":
            depth -= 1
            continue
        if kind == "ident" and index + 1 < len(tokens) and depth > 0:
            nxt = tokens[index + 1]
            if nxt[0] == "op" and nxt[1] == "(":
                return [_diag("Q_AGG_ARITY", ctx, field=value,
                              detail="聚合函数不允许嵌套")]
    return []


def scan_agg(ctx: dict) -> list[dict]:
    out: list[dict] = []
    for name, _arg in agg_calls(ctx):
        if name.lower() == "ref":
            continue
        if contract.canonical_agg(name) is None:
            out.append(_diag("Q_AGG_UNKNOWN", ctx, field=name, raw_value=name))
    return out


def scan_sentinel(ctx: dict) -> list[dict]:
    out: list[dict] = []
    for name, arg in agg_calls(ctx):
        if name.lower() == "ref":
            continue
        if coerce.is_sentinel(arg):
            out.append(_diag("Q_SENTINEL_VALUE", ctx, field=name, raw_value=arg))
    match = WHERE_RE.search(ctx["norm"])
    if match and coerce.is_sentinel(match.group(2)):
        out.append(_diag("Q_SENTINEL_VALUE", ctx, field=match.group(1),
                         raw_value=match.group(2)))
    return out


def scan_field(ctx: dict) -> list[dict]:
    out: list[dict] = []
    for name, arg in agg_calls(ctx):
        if name.lower() == "ref" or coerce.is_sentinel(arg):
            continue
        if contract.resolve_field(arg) is None:
            out.append(_diag("Q_FIELD_UNKNOWN", ctx, field=arg, raw_value=arg))
    match = WHERE_RE.search(ctx["norm"])
    if match and contract.resolve_field(match.group(1)) is None:
        out.append(_diag("Q_FIELD_UNKNOWN", ctx, field=match.group(1),
                         raw_value=match.group(1)))
    return out


def scan_group(ctx: dict) -> list[dict]:
    match = GROUP_RE.search(ctx["norm"])
    if not match:
        return []
    out: list[dict] = []
    for dim in re.split(r"[,\s]+", match.group(1).strip()):
        if not dim:
            continue
        if not contract.is_dimension(dim):
            out.append(_diag("Q_GROUP_INVALID", ctx, field=dim, raw_value=dim))
    return out


SCANS = (scan_assign, scan_name, scan_parens, scan_nested_agg,
         scan_agg, scan_sentinel, scan_field, scan_group)


def dedupe(diags: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for item in diags:
        key = (item["code"], item.get("field") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def ordered(diags: list[dict]) -> list[dict]:
    return sorted(diags, key=lambda d: (d.get("line_no") or 0,
                                        d.get("rank", len(config.DIAG_ORDER)),
                                        d["code"]))


def build_definition(line_no: int, raw: str, ast: dict) -> dict:
    fields: list[str] = []
    metrics: list[str] = []
    aggs: list[str] = []
    grammar.walk(ast["expr"], fields=fields, metrics=metrics, aggs=aggs)
    group_by = [contract.resolve_field(dim) or dim for dim in ast["group_by"]]
    where = ast["where"]
    if where:
        where = {"field": contract.resolve_field(where["field"]) or where["field"],
                 "op": where["op"], "value": str(where["value"])}
    return {
        "name": ast["name"],
        "line_no": line_no,
        "raw": raw,
        "signature": grammar.signature(ast["name"], ast),
        "expr": ast["expr"],
        "expr_text": grammar.expr_text(ast["expr"]),
        "where": where,
        "group_by": group_by,
        "fields": sorted(set(fields)),
        "metrics": sorted(set(metrics)),
        "aggregators": sorted(set(aggs)),
        "depends_declared": list(ast["depends_declared"]),
        "note": "",
    }


def inspect_line(line_no: int, raw: str, *, scans=SCANS) -> dict:
    ctx = context(line_no, raw)
    found: list[dict] = []
    for scan in scans:
        found.extend(scan(ctx))
    if not any(item["level"] == reasons.ERROR for item in found):
        try:
            ast = grammar.parse(raw)
        except grammar.ParseError as exc:
            found.append(_diag(exc.code, ctx, raw_value=ctx["norm"][:60],
                               detail=exc.message))
        else:
            definition = build_definition(line_no, raw, ast)
            return {"definition": definition,
                    "diagnostics": ordered(dedupe(found))}
    return {"definition": None, "diagnostics": ordered(dedupe(found))}
