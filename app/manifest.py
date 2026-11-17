"""运行清单：run_id、输入摘要、规则版本、参数、耗时，可复算。

run_id 人读短、机读唯一；输入摘要对每份输入单独算 sha256，再合成批次键。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import uuid

from . import config


def new_run_id(prefix: str = "MR") -> str:
    stamp = dt.datetime.now(config.UTC).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:4]}"


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_text(text: str) -> str:
    return digest_bytes(text.encode("utf-8"))


def digest_parts(parts: list[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def batch_key(*, dsl_text: str, versions_digest: str, reports_digest: str,
              rule_version: str) -> str:
    """批次键只由输入内容与规则版本决定；参数不影响结果故不参与。"""
    return digest_parts([dsl_text, versions_digest, reports_digest, rule_version])[:32]


def build(*, run_id: str, batch_id: str, batch_key_value: str, settings,
          source: str, inputs: list[dict], params: dict, started_at: str,
          finished_at: str, elapsed_ms: int, stages: list[dict],
          counters: dict) -> dict:
    return {
        "run_id": run_id,
        "batch_id": batch_id,
        "batch_key": batch_key_value,
        "source": source,
        "rule_version": settings.rule_version,
        "eval_date": settings.eval_date.isoformat(),
        "decimals": "权重 Decimal，2 位最小刻度",
        "version_window": "有效期半开区间 [valid_from, valid_to)",
        "inputs": inputs,
        "params": params,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_ms": elapsed_ms,
        "stages": stages,
        "counters": counters,
        "replayable": "同一 batch_key 重跑返回同一批次，不新增行",
    }
