"""诊断分布与通过率：只统计，不做判定。"""
from __future__ import annotations

from ... import reasons


def distribution(diags: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for item in diags:
        counts[item["code"]] = counts.get(item["code"], 0) + 1
    rows = []
    for code, count in counts.items():
        reason = reasons.get(code)
        rows.append({
            "code": code, "count": count, "level": reason.level,
            "level_label": reasons.LEVEL_LABELS[reason.level],
            "stage": reason.stage, "title": reason.title,
        })
    rows.sort(key=lambda r: (reasons.LEVEL_ORDER[r["level"]], -r["count"], r["code"]))
    return rows


def by_level(diags: list[dict]) -> dict:
    out = {level: 0 for level in (reasons.ERROR, reasons.WARN, reasons.INFO)}
    for item in diags:
        out[item["level"]] = out.get(item["level"], 0) + 1
    return out


def isolated_line_numbers(diags: list[dict]) -> list[int]:
    lines = {item["line_no"] for item in diags
             if item["level"] == reasons.ERROR and item.get("line_no")}
    return sorted(lines)


def pass_rate(summary: dict, isolated: int) -> dict:
    definitions = summary.get("definition", 0)
    registered = definitions - isolated
    percent = 0.0 if definitions == 0 else round(registered * 100.0 / definitions, 1)
    return {"definitions": definitions, "registered": registered,
            "isolated": isolated, "percent": percent}
