"""版本提交：只接受比库中最新版本更晚的提交，陈旧提交返回 409。

没有版本比较就会「后提交无条件覆盖」——两个组同时改同一指标时，
先改的那份被静默丢掉，页面上看不出来（TRAP-26）。
"""
from __future__ import annotations

import datetime as dt

from ... import config, errors, reasons
from . import intervals


def latest_version(rows: list[dict], metric: str) -> int:
    versions = [r["version"] for r in rows if r["metric"] == metric]
    return max(versions) if versions else 0


def validate(payload: dict) -> dict:
    metric = (payload.get("metric") or "").strip()
    if not metric:
        raise errors.BadRequest("缺少指标名", code="Q_NAME_INVALID")
    try:
        version = int(payload.get("version"))
    except (TypeError, ValueError) as exc:
        raise errors.BadRequest("版本号必须是整数", code="V_INTERVAL_INVERTED") from exc
    valid_from = intervals.parse_date(payload.get("valid_from") or "")
    if valid_from is None:
        raise errors.BadRequest("valid_from 不是日期", code="V_INTERVAL_INVERTED")
    valid_to = intervals.parse_date(payload.get("valid_to") or "") or None
    if valid_to is not None and valid_to <= valid_from:
        raise errors.BadRequest("valid_to 必须晚于 valid_from", code="V_INTERVAL_INVERTED")
    return {"metric": metric, "version": version,
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat() if valid_to else config.OPEN_END,
            "valid_to_text": valid_to.isoformat() if valid_to else "",
            "author": (payload.get("author") or "手工提交").strip(),
            "submitted_at": dt.datetime.now(config.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "OK", "note": "手工提交", "line_no": None}


def submit(store, batch: dict, payload: dict) -> dict:
    metric_name = (payload.get("metric") or "").strip()
    metric = store.find_metric(batch["batch_id"], metric_name)
    if metric is None:
        raise errors.NotFound(f"指标未注册：{metric_name}", code="G_REF_UNKNOWN")
    rows = store.load_versions(batch["batch_id"])
    current = latest_version(rows, metric_name)
    candidate = validate(payload)
    if candidate["version"] <= current:
        reason = reasons.get("V_STALE_SUBMIT")
        raise errors.Conflict(
            f"提交版本 v{candidate['version']} 不晚于库中最新 v{current}",
            code="V_STALE_SUBMIT",
            detail={"metric": metric_name, "current": current,
                    "submitted": candidate["version"], "hint": reason.hint})
    # 只有真正与已有区间重叠时才把相关行标成 OVERLAP，不整列刷状态
    overlapped = [row for row in rows
                  if row["metric"] == metric_name
                  and intervals.overlaps(candidate, row)]
    if overlapped:
        candidate["status"] = "OVERLAP"
    store.insert_version(batch["batch_id"], candidate)
    for row in overlapped:
        store.set_version_status(batch["batch_id"], metric_name, row["version"], "OVERLAP")
    refreshed = store.load_versions(batch["batch_id"])
    diagnostics = intervals.check(refreshed)
    return {"accepted": True, "metric": metric_name,
            "version": candidate["version"], "previous": current,
            "overlapped": [row["version"] for row in overlapped],
            "diagnostics": [{"code": d["code"], "line_no": d["line_no"],
                             "detail": d["detail"]} for d in diagnostics]}
