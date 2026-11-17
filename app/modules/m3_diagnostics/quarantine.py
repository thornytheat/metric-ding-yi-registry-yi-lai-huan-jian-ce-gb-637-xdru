"""隔离区导出：行号 + 原因码 + 原值，给人工复核用。

导出带 UTF-8 BOM（表格软件双击不乱码），列序固定，不用中文表头以外的装饰。
"""
from __future__ import annotations

import csv
import io

COLUMNS = ("line_no", "code", "level", "stage", "metric", "field", "raw_value", "detail")
HEADERS = {
    "line_no": "行号",
    "code": "原因码",
    "level": "级别",
    "stage": "阶段",
    "metric": "指标",
    "field": "字段",
    "raw_value": "原值",
    "detail": "结论",
}


def to_csv_text(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([HEADERS[c] for c in COLUMNS])
    for row in rows:
        writer.writerow(["" if row.get(c) is None else row.get(c) for c in COLUMNS])
    return buffer.getvalue()


def export_rows(diags: list[dict]) -> list[dict]:
    return [dict(row) for row in diags]
