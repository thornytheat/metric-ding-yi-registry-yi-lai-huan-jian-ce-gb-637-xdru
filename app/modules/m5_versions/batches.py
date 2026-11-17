"""批次历史视图：把清单里的输入摘要与账目拼成一行，供页面与导出复用。"""
from __future__ import annotations

from ... import reasons


def summarize(batch: dict, totals: dict, manifest: dict | None) -> dict:
    manifest = manifest or {}
    inputs = manifest.get("inputs") or []
    return {
        "batch_id": batch["batch_id"],
        "batch_key": batch["batch_key"][:12],
        "run_id": batch["run_id"],
        "source": batch["source"],
        "status": batch["status"],
        "created_at": batch["created_at"],
        "finished_at": batch.get("finished_at") or "",
        "input_digest": batch["input_digest"][:12],
        "note": batch.get("note", ""),
        "lines": totals.get("lines_total", "0"),
        "registered": totals.get("metrics_registered", "0"),
        "isolated": totals.get("lines_isolated", "0"),
        "cycles": totals.get("cycle_count", "0"),
        "elapsed_ms": manifest.get("elapsed_ms", 0),
        "inputs": inputs,
    }


def history(store, limit: int = 20) -> list[dict]:
    rows = []
    for batch in store.list_batches(limit=limit):
        totals = store.load_totals(batch["batch_id"])
        rows.append(summarize(batch, totals, store.load_manifest(batch["batch_id"])))
    return rows


def replay_note(reused: bool) -> str:
    if not reused:
        return ""
    return reasons.get("B_IDEMPOTENT_REPLAY").title
