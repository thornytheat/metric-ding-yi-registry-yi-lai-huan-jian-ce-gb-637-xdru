"""DSL 词法与语法：一行一条定义，返回语法树与检出项。

文法（子句顺序任意，各最多一次）：
    name = expr [where field = value] [group by dim, ...] [depends: name, ...]
    expr   := term (('+'|'-') term)*
    term   := factor (('*'|'/') factor)*
    factor := agg '(' field ')' | ref '(' name ')' | number | '(' expr ')'

解析失败只抛一个 ParseError；结构性检查（括号、哨兵、字段）在 m3 的扫描里
独立完成，两条路径互不依赖，所以规则顺序不影响结果。
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from . import coerce, contract

TOKEN_RE = re.compile(
    r"(?P<ws>\s+)"
    r"|(?P<num>\d+(?:\.\d+)?)"
    r"|(?P<ident>[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*)"
    r"|(?P<op>[=+\-*/(),:.])"
    r"|(?P<other>.)"
)

CLAUSE_KEYWORDS = ("where", "group", "depends")
MAX_DEPTH = 32


class ParseError(Exception):
    def __init__(self, code: str, message: str, position: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.position = position


def tokenize(text: str) -> list[tuple[str, str, int]]:
    tokens: list[tuple[str, str, int]] = []
    for match in TOKEN_RE.finditer(text):
        kind = match.lastgroup or "other"
        if kind == "ws":
            continue
        tokens.append((kind, match.group(), match.start()))
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str, int]]):
        self.tokens = tokens
        self.index = 0
        self.depth = 0

    # ---- 基础操作 ----
    def peek(self) -> tuple[str, str, int] | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> tuple[str, str, int]:
        token = self.peek()
        if token is None:
            raise ParseError("Q_EXPR_EMPTY", "表达式意外结束", None)
        self.index += 1
        return token

    def accept(self, kind: str, value: str | None = None) -> tuple[str, str, int] | None:
        token = self.peek()
        if token is None or token[0] != kind:
            return None
        if value is not None and token[1] != value:
            return None
        self.index += 1
        return token

    def expect_op(self, value: str) -> tuple[str, str, int]:
        token = self.accept("op", value)
        if token is None:
            current = self.peek()
            got = current[1] if current else "行尾"
            code = "Q_PAREN_UNBALANCED" if value == ")" else "Q_NO_ASSIGN"
            raise ParseError(code, f"期望 {value}，实际是 {got}")
        return token

    # ---- 语法 ----
    def parse(self) -> dict:
        name_token = self.accept("ident")
        if name_token is None:
            raise ParseError("Q_NAME_INVALID", "赋值号左侧不是指标名")
        name = name_token[1]
        if not coerce.is_identifier(name):
            raise ParseError("Q_NAME_INVALID", f"指标名不合法：{name}", name_token[2])
        self.expect_op("=")
        if self.peek() is None:
            raise ParseError("Q_EXPR_EMPTY", "赋值号右侧为空")
        expr_ast = self.expr(1)
        where = None
        group_by: list[str] = []
        depends: list[str] = []
        while True:
            token = self.peek()
            if token is None or token[0] != "ident":
                break
            keyword = token[1].lower()
            if keyword not in CLAUSE_KEYWORDS:
                break
            self.index += 1
            if keyword == "where":
                if where is not None:
                    raise ParseError("Q_WHERE_INVALID", "where 子句重复")
                where = self.parse_where()
            elif keyword == "group":
                if group_by:
                    raise ParseError("Q_GROUP_INVALID", "group by 子句重复")
                group_by = self.parse_group()
            else:
                if depends:
                    raise ParseError("Q_DEP_INVALID", "depends 子句重复")
                depends = self.parse_depends()
        if self.peek() is not None:
            leftover = self.peek()
            raise ParseError("Q_TOKEN_EXTRA", f"多余记号：{leftover[1]}", leftover[2])
        return {
            "name": name,
            "expr": expr_ast,
            "where": where,
            "group_by": group_by,
            "depends_declared": depends,
        }

    def parse_where(self) -> dict:
        field_token = self.accept("ident")
        if field_token is None:
            raise ParseError("Q_WHERE_INVALID", "where 后缺字段名")
        if self.accept("op", "=") is None:
            raise ParseError("Q_WHERE_INVALID", "过滤条件只支持 field = value")
        value_token = self.peek()
        if value_token is None or value_token[0] not in {"ident", "num"}:
            raise ParseError("Q_WHERE_INVALID", "过滤条件缺取值")
        self.index += 1
        return {"field": field_token[1], "op": "=", "value": value_token[1]}

    def parse_group(self) -> list[str]:
        keyword = self.accept("ident")
        if keyword is None or keyword[1].lower() != "by":
            raise ParseError("Q_GROUP_INVALID", "group 后缺 by")
        dims: list[str] = []
        while True:
            token = self.accept("ident")
            if token is None:
                raise ParseError("Q_GROUP_INVALID", "group by 后缺维度名")
            dims.append(token[1])
            if self.accept("op", ",") is None:
                break
        return dims

    def parse_depends(self) -> list[str]:
        if self.accept("op", ":") is None:
            raise ParseError("Q_DEP_INVALID", "depends 后缺冒号")
        names: list[str] = []
        while True:
            token = self.accept("ident")
            if token is None:
                raise ParseError("Q_DEP_INVALID", "depends 后缺指标名")
            names.append(token[1])
            if self.accept("op", ",") is None:
                break
        return names

    def expr(self, min_prec: int):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ParseError("Q_PAREN_UNBALANCED", "表达式嵌套过深或括号未闭合")
        left = self.factor()
        while True:
            token = self.peek()
            if token is None or token[0] != "op" or token[1] not in "+-*/":
                break
            prec = 1 if token[1] in "+-" else 2
            if prec < min_prec:
                break
            self.index += 1
            right = self.expr(prec + 1)
            left = {"op": token[1], "left": left, "right": right}
        self.depth -= 1
        return left

    def factor(self):
        token = self.peek()
        if token is None:
            raise ParseError("Q_EXPR_EMPTY", "表达式意外结束")
        if token[0] == "num":
            self.index += 1
            try:
                return {"kind": "const", "value": str(Decimal(token[1]))}
            except InvalidOperation as exc:  # pragma: no cover - 词法已保证可解析
                raise ParseError("Q_TOKEN_EXTRA", f"常量不合法：{token[1]}") from exc
        if token[0] == "op" and token[1] == "(":
            self.index += 1
            inner = self.expr(1)
            self.expect_op(")")
            return {"kind": "group", "expr": inner}
        if token[0] == "ident":
            self.index += 1
            lowered = token[1].lower()
            if lowered == "ref":
                self.expect_op("(")
                target = self.accept("ident")
                if target is None:
                    raise ParseError("Q_AGG_ARITY", "ref() 缺指标名")
                self.expect_op(")")
                return {"kind": "ref", "name": target[1]}
            agg = contract.canonical_agg(token[1])
            if agg is None:
                if self.peek() is not None and self.peek()[0] == "op" \
                        and self.peek()[1] == "(":
                    raise ParseError("Q_AGG_UNKNOWN", f"聚合函数不在白名单：{token[1]}")
                return {"kind": "const_ref", "value": token[1]}
            self.expect_op("(")
            arg = self.peek()
            if arg is None or arg[0] != "ident":
                raise ParseError("Q_AGG_ARITY", f"{agg}() 参数必须是单个字段名")
            self.index += 1
            if self.peek() is not None and self.peek()[0] == "op" \
                    and self.peek()[1] == ",":
                raise ParseError("Q_AGG_ARITY", f"{agg}() 只接受一个参数")
            self.expect_op(")")
            return {"kind": "agg", "agg": agg, "field": arg[1]}
        if token[0] == "op" and token[1] == ")":
            raise ParseError("Q_PAREN_UNBALANCED", "多出一个右括号")
        raise ParseError("Q_EXPR_EMPTY", f"无法解析的记号：{token[1]}")


def parse(text: str) -> dict:
    tokens = tokenize(coerce.normalize_punct(text))
    if not tokens:
        raise ParseError("Q_EXPR_EMPTY", "该行没有可解析内容")
    return _Parser(tokens).parse()


def walk(node, *, fields: list[str], metrics: list[str], aggs: list[str]) -> None:
    if node is None:
        return
    kind = node.get("kind")
    if kind == "agg":
        canonical = contract.resolve_field(node["field"]) or node["field"]
        fields.append(canonical)
        aggs.append(node["agg"])
    elif kind == "ref":
        metrics.append(node["name"])
    elif kind == "group":
        walk(node["expr"], fields=fields, metrics=metrics, aggs=aggs)
    elif "left" in node:
        walk(node["left"], fields=fields, metrics=metrics, aggs=aggs)
        walk(node["right"], fields=fields, metrics=metrics, aggs=aggs)


def expr_text(node) -> str:
    if node is None:
        return ""
    kind = node.get("kind")
    if kind == "agg":
        canonical = contract.resolve_field(node["field"]) or node["field"]
        return f"{node['agg']}({canonical})"
    if kind == "ref":
        return f"ref({node['name']})"
    if kind == "const":
        return node["value"]
    if kind == "const_ref":
        return node["value"]
    if kind == "group":
        return f"({expr_text(node['expr'])})"
    return f"{expr_text(node['left'])}{node['op']}{expr_text(node['right'])}"


def signature(name: str, ast: dict) -> str:
    where = ast.get("where")
    where_text = "" if not where else \
        f"|where={contract.resolve_field(where['field']) or where['field']}={where['value']}"
    group_text = ",".join(
        contract.resolve_field(dim) or dim for dim in ast.get("group_by") or [])
    dep_text = ",".join(sorted(ast.get("depends_declared") or []))
    return f"{name}={expr_text(ast['expr'])}{where_text}|group={group_text}|depends={dep_text}"
