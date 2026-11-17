"""JSON 导出：Decimal 一律字符串，大整数不经 float 往返。"""
from __future__ import annotations

import json
from decimal import Decimal


def _default(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"不可序列化：{type(value).__name__}")


def dumps(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=_default)


def loads(text: str):
    return json.loads(text)


def manifest_payload(batch: dict, manifest: dict) -> dict:
    return {
        "batch_id": batch["batch_id"],
        "batch_key": batch["batch_key"],
        "run_id": batch["run_id"],
        "input_digest": batch["input_digest"],
        "status": batch["status"],
        "manifest": manifest,
    }
