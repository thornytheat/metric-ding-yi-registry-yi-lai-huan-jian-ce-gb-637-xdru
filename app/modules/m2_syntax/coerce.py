"""写法归一：全角转半角、哨兵判定、Decimal 化、标识符判定。

全角逗号、全角括号、全角等号、全角数字、全角减号在真实录入里很常见，
不先归一，词法分析会把一条定义切成两半。
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ... import config

_FULLWIDTH_TABLE = {cp: cp - 0xFEE0 for cp in range(0xFF01, 0xFF5F)}
_FULLWIDTH_TABLE[0x3000] = 0x20      # 全角空格
_FULLWIDTH_TABLE[0x3001] = 0x2C      # 顿号当作逗号
_FULLWIDTH_TABLE[0x3002] = 0x2E      # 句号当作点

IDENT_RE = re.compile(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*$")
RESERVED = frozenset({"where", "group", "by", "depends", "ref", "and", "or"})


def normalize_punct(text: str) -> str:
    return text.translate(_FULLWIDTH_TABLE)


def is_identifier(text: str) -> bool:
    return bool(IDENT_RE.match(text or "")) and (text or "").lower() not in RESERVED


def is_sentinel(value) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in config.SENTINELS


def to_decimal(text) -> Decimal | None:
    body = str(text).strip().replace(",", "")
    if is_sentinel(body):
        return None
    try:
        return Decimal(body)
    except (InvalidOperation, ValueError):
        return None


def quantize(value: Decimal) -> Decimal:
    return value.quantize(config.DECIMAL_QUANT)


def squash(text: str) -> str:
    return re.sub(r"\s+", "", normalize_punct(text))
