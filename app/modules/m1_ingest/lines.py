"""行分类：空行 / 注释 / 定义；空输入三态给出三个不同原因码。

三态分开是为了让 0 字符、全空行、只有注释返回不同结论，
而不是一律「成功解析 0 条」。
"""
from __future__ import annotations

from .reader import RawLine

COMMENT_PREFIXES = ("#", "--", "//")


def classify(raw: str) -> str:
    body = raw.strip()
    if body == "":
        return "blank"
    for prefix in COMMENT_PREFIXES:
        if body.startswith(prefix):
            return "comment"
    return "definition"


def summarize(rows: list[RawLine]) -> dict:
    counts = {"blank": 0, "comment": 0, "definition": 0}
    for row in rows:
        counts[classify(row.raw)] += 1
    return {"total": len(rows), **counts}


def empty_state(summary: dict) -> str | None:
    """返回空态原因码；有定义行时返回 None。"""
    if summary["total"] == 0:
        return "E_EMPTY_INPUT"
    if summary["definition"] > 0:
        return None
    if summary["comment"] > 0:
        return "E_EMPTY_COMMENTS"
    return "E_EMPTY_BLANKS"


def to_records(rows: list[RawLine]) -> list[dict]:
    return [{"line_no": r.line_no, "kind": classify(r.raw), "raw": r.raw,
             "state": "pending", "code": None} for r in rows]
