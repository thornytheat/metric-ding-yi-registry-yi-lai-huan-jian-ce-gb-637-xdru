"""导出：指标清单、依赖边、冲突表，全部 UTF-8 BOM + LF。"""
from __future__ import annotations

import csv
import io

METRIC_COLUMNS = (
    ("line_no", "行号"), ("name", "指标"), ("expr_text", "表达式"),
    ("where", "过滤"), ("group_by", "分组"), ("fields", "字段"),
    ("aggregators", "聚合"), ("depends_declared", "声明依赖"),
)
EDGE_COLUMNS = (("kind", "类型"), ("src", "起点"), ("dst", "终点"))
CONFLICT_COLUMNS = (
    ("metric", "指标"), ("level_label", "等级"), ("kept_line", "保留行"),
    ("other_line", "冲突行"), ("diff", "差异"),
)


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    if isinstance(value, dict):
        return " ".join(f"{k}={v}" for k, v in value.items())
    return str(value)


def to_csv_text(rows: list[dict], columns) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([_cell(row.get(key)) for key, _ in columns])
    return buffer.getvalue()


def metrics_csv(metrics: list[dict]) -> str:
    return to_csv_text(metrics, METRIC_COLUMNS)


def edges_csv(edges: list[dict]) -> str:
    return to_csv_text(edges, EDGE_COLUMNS)


def conflicts_csv(conflicts: list[dict]) -> str:
    return to_csv_text(conflicts, CONFLICT_COLUMNS)
