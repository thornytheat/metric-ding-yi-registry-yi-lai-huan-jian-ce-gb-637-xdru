"""版本有效期：半开区间 [valid_from, valid_to)，valid_to 留空表示未关闭。

相邻区间不算重叠（前者到 7-01 结束，后者 7-01 开始），这是端点归属的
显式声明；两端都算的实现会误报，一端都不算的实现会漏报。
"""
from __future__ import annotations

import csv
import datetime as dt
import io

from ... import config, reasons


def _rank(code: str) -> int:
    try:
        return config.DIAG_ORDER.index(code)
    except ValueError:
        return len(config.DIAG_ORDER)


def _diag(code: str, line_no: int | None, metric: str | None,
          raw_value: str | None, detail: str = "") -> dict:
    reason = reasons.get(code)
    return {"code": code, "level": reason.level, "stage": reason.stage,
            "line_no": line_no, "metric": metric, "field": "version",
            "raw_value": raw_value, "detail": detail or reason.title,
            "rank": _rank(code)}


def parse_date(text: str) -> dt.date | None:
    body = (text or "").strip()
    if not body:
        return None
    try:
        return dt.date.fromisoformat(body)
    except ValueError:
        return None


def parse_versions_text(text: str) -> dict:
    rows: list[dict] = []
    diagnostics: list[dict] = []
    reader = csv.DictReader(io.StringIO(text))
    for index, raw in enumerate(reader, start=2):
        metric = (raw.get("metric") or "").strip()
        version_text = (raw.get("version") or "").strip()
        if not metric:
            continue
        try:
            version = int(version_text)
        except ValueError:
            diagnostics.append(_diag("V_INTERVAL_INVERTED", None, metric, version_text,
                                     f"台账第 {index} 行版本号不是整数："
                                     f"{version_text or '空'}"))
            continue
        valid_from = parse_date(raw.get("valid_from") or "")
        valid_to = parse_date(raw.get("valid_to") or "")
        status = "OK"
        note = ""
        if valid_from is None:
            diagnostics.append(_diag("V_INTERVAL_INVERTED", None, metric,
                                     raw.get("valid_from") or "",
                                     f"台账第 {index} 行 valid_from 缺失或不是日期"))
            status = "BAD_FROM"
        elif valid_to is not None and valid_to <= valid_from:
            diagnostics.append(_diag("V_INTERVAL_INVERTED", None, metric,
                                     f"{valid_from}~{valid_to}",
                                     f"台账第 {index} 行起止倒挂，valid_to 必须晚于 valid_from"))
            status = "INVERTED"
        rows.append({
            "metric": metric,
            "version": version,
            "valid_from": (valid_from or dt.date(1970, 1, 1)).isoformat(),
            "valid_to": valid_to.isoformat() if valid_to else config.OPEN_END,
            "valid_to_text": valid_to.isoformat() if valid_to else "",
            "author": (raw.get("author") or "").strip(),
            "submitted_at": (raw.get("submitted_at") or "").strip(),
            "status": status,
            "note": note,
            "line_no": index,
        })
    return {"rows": rows, "diagnostics": diagnostics}


def overlaps(a: dict, b: dict) -> bool:
    return a["valid_from"] < b["valid_to"] and b["valid_from"] < a["valid_to"]


def check(rows: list[dict]) -> list[dict]:
    """只检查区间本身，不检查指标是否注册（注册与否在图阶段说清）。"""
    diagnostics: list[dict] = []
    by_metric: dict[str, list[dict]] = {}
    for row in rows:
        by_metric.setdefault(row["metric"], []).append(row)
    for metric, group in sorted(by_metric.items()):
        ordered = sorted(group, key=lambda r: (r["valid_from"], r["version"]))
        for index, first in enumerate(ordered):
            for second in ordered[index + 1:]:
                if not overlaps(first, second):
                    continue
                for row in (first, second):
                    if row["status"] == "OK":
                        row["status"] = "OVERLAP"
                diagnostics.append(_diag(
                    "V_INTERVAL_OVERLAP", None, metric,
                    f"v{first['version']} {first['valid_from']}~{first['valid_to']} "
                    f"与 v{second['version']} {second['valid_from']}~{second['valid_to']}",
                    f"v{first['version']} 与 v{second['version']} 同时生效"))
    return diagnostics


def covers(row: dict, day: dt.date) -> bool:
    start = dt.date.fromisoformat(row["valid_from"])
    end = dt.date.fromisoformat(row["valid_to"])
    return start <= day < end


def status_label(status: str) -> str:
    return {
        "OK": "有效",
        "OVERLAP": "区间重叠",
        "INVERTED": "起止倒挂",
        "BAD_FROM": "起始无效",
        "UNKNOWN": "未注册",
    }.get(status, status)
