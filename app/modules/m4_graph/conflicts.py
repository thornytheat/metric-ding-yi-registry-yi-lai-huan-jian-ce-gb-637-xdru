"""同名指标冲突：保留首次定义，其余按差异种类分三级。

代表元规则写死为「行号最小的那一条」，不依赖输入顺序的偶然性，
冲突记录里带两条行号与差异字段，便于导出成变更单（TRAP-14 的归因要求）。
"""
from __future__ import annotations

from ... import config, reasons
from ..m2_syntax import contract


def diff_kinds(kept: dict, other: dict) -> list[str]:
    kinds: list[str] = []
    if set(kept["aggregators"]) != set(other["aggregators"]):
        kinds.append("aggregators")
    if kept["expr_text"] != other["expr_text"]:
        kinds.append("expr")
    if (kept["where"] or None) != (other["where"] or None):
        kinds.append("where")
    if (kept["group_by"] or []) != (other["group_by"] or []):
        kinds.append("group_by")
    if sorted(kept["depends_declared"]) != sorted(other["depends_declared"]):
        kinds.append("depends")
    if not kinds:
        kinds.append("expr")
    return kinds


LEVEL_CODE = {
    "BLOCK": "C_DUP_NAME_BLOCK",
    "REVIEW": "C_DUP_NAME_REVIEW",
    "INFO": "C_DUP_NAME_INFO",
}


def resolve(candidates: list[dict]) -> dict:
    kept: list[dict] = []
    by_name: dict[str, dict] = {}
    conflicts: list[dict] = []
    diagnostics: list[dict] = []
    for item in sorted(candidates, key=lambda c: c["line_no"]):
        name = item["name"]
        keeper = by_name.get(name)
        if keeper is None:
            by_name[name] = item
            kept.append(item)
            continue
        kinds = diff_kinds(keeper, item)
        level = contract.conflict_level(kinds)
        code = LEVEL_CODE[level]
        reason = reasons.get(code)
        conflicts.append({
            "metric": name,
            "level": level,
            "level_label": config.CONFLICT_LEVEL_LABELS[level],
            "kept_line": keeper["line_no"],
            "other_line": item["line_no"],
            "diff": kinds,
            "detail": f"保留第 {keeper['line_no']} 行，第 {item['line_no']} 行入冲突表",
        })
        diagnostics.append({
            "code": code, "level": reason.level, "stage": reason.stage,
            "line_no": item["line_no"], "metric": name, "field": "name",
            "raw_value": item["signature"], "detail": reason.title,
            "rank": _rank(code),
        })
    return {"metrics": kept, "conflicts": conflicts, "diagnostics": diagnostics}


def _rank(code: str) -> int:
    try:
        return config.DIAG_ORDER.index(code)
    except ValueError:
        return len(config.DIAG_ORDER)
