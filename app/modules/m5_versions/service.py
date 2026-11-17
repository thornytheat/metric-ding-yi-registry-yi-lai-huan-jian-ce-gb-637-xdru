"""M5 编排：读版本台账 → 区间核验 → 版本视图。"""
from __future__ import annotations

from pathlib import Path

from . import batches, intervals


def load(settings, metrics: list[dict]) -> dict:
    path = Path(settings.sample_dir) / "metric_versions.csv"
    text = path.read_text(encoding="utf-8-sig")
    parsed = intervals.parse_versions_text(text)
    rows = parsed["rows"]
    diagnostics = list(parsed["diagnostics"])
    diagnostics.extend(intervals.check(rows))
    registered = {m["name"] for m in metrics}
    for row in rows:
        if row["metric"] not in registered and row["status"] == "OK":
            row["status"] = "UNKNOWN"
        row["status_label"] = intervals.status_label(row["status"])
    diagnostics.sort(key=lambda d: (d["line_no"] or 0, d["code"]))
    return {"rows": rows, "diagnostics": diagnostics, "registered": sorted(registered)}


def view(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "rows": rows,
        "counts": counts,
        "total": len(rows),
        "metrics": sorted({row["metric"] for row in rows}),
        "conflict_rows": [r for r in rows if r["status"] in {"OVERLAP", "INVERTED"}],
    }


def history(store) -> list[dict]:
    return batches.history(store)
