"""M3 编排：逐行诊断、完全重复行合并、分布统计、过滤视图。"""
from __future__ import annotations

import time

from ... import reasons
from ..m1_ingest import lines as lines_mod
from . import metrics, quarantine, rules


def inspect_lines(rows) -> dict:
    """rows 来自 m1 的 RawLine 列表；返回指标、诊断与行状态。"""
    started = time.perf_counter()
    diags: list[dict] = []
    records: list[dict] = []
    candidates: list[dict] = []
    seen: dict[str, int] = {}
    for row in rows:
        kind = lines_mod.classify(row.raw)
        record = {"line_no": row.line_no, "kind": kind, "raw": row.raw,
                  "state": kind, "code": None}
        if kind != "definition":
            records.append(record)
            continue
        result = rules.inspect_line(row.line_no, row.raw)
        line_diags = result["diagnostics"]
        definition = result["definition"]
        if definition is not None:
            first_line = seen.get(definition["signature"])
            if first_line is not None:
                line_diags = line_diags + [rules._diag(
                    "Q_DUP_LINE", rules.context(row.line_no, row.raw),
                    raw_value=definition["name"],
                    detail=f"与第 {first_line} 行定义完全相同，本行隔离")]
                definition = None
            else:
                seen[definition["signature"]] = row.line_no
        diags.extend(line_diags)
        has_error = any(item["level"] == reasons.ERROR for item in line_diags)
        if definition is not None and not has_error:
            candidates.append(definition)
            record["state"] = "registered"
        else:
            record["state"] = "isolated"
            record["code"] = next(
                (item["code"] for item in line_diags if item["level"] == reasons.ERROR),
                line_diags[0]["code"] if line_diags else None)
        records.append(record)
    ordered = rules.ordered(diags)
    elapsed = int((time.perf_counter() - started) * 1000)
    return {
        "metrics": candidates,
        "diagnostics": ordered,
        "lines": records,
        "isolated_lines": metrics.isolated_line_numbers(ordered),
        "elapsed_ms": elapsed,
    }


def view(diags: list[dict], *, code: str | None = None, level: str | None = None,
         stage: str | None = None, line_no: int | None = None) -> dict:
    filtered = diags
    if code:
        filtered = [d for d in filtered if d["code"] == code]
    if level:
        filtered = [d for d in filtered if d["level"] == level]
    if stage:
        filtered = [d for d in filtered if d["stage"] == stage]
    if line_no:
        filtered = [d for d in filtered if d.get("line_no") == line_no]
    return {
        "rows": filtered,
        "total": len(diags),
        "filtered": len(filtered),
        "distribution": metrics.distribution(diags),
        "by_level": metrics.by_level(diags),
        "filters": {"code": code or "", "level": level or "",
                    "stage": stage or "", "line_no": line_no or ""},
        "codes": sorted({d["code"] for d in diags}),
    }


def export_csv(diags: list[dict]) -> str:
    return quarantine.to_csv_text(quarantine.export_rows(diags))
