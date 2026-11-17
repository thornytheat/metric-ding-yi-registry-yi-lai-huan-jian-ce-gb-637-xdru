"""字节 → 文本：BOM 剥离、编码回退链、声明编码只作首个候选。

回退链顺序固定：utf-8-sig（顺带剥 BOM）→ utf-8 → gb18030。
声明编码先按别名归一，只影响首选，不阻止回退（TRAP-02：BOM 进首列名）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ... import config

CHARSET_ALIASES = {
    "gb2312": "gb18030",
    "gbk": "gb18030",
    "gb18030": "gb18030",
    "utf8": "utf-8",
    "utf-8": "utf-8",
    "utf-8-sig": "utf-8-sig",
    "utf_8": "utf-8",
}


@dataclass
class Decoded:
    text: str
    encoding: str
    bom_stripped: bool = False
    fallback: bool = False
    flags: list[str] = field(default_factory=list)


def normalize_declared(declared: str | None) -> str | None:
    if not declared:
        return None
    return CHARSET_ALIASES.get(declared.strip().lower(), declared.strip().lower())


def chain_for(declared: str | None) -> tuple[str, ...]:
    first = normalize_declared(declared)
    chain = list(config.ENCODING_CHAIN) if hasattr(config, "ENCODING_CHAIN") else \
        ["utf-8-sig", "utf-8", "gb18030"]
    if first and first in chain:
        chain.remove(first)
        chain.insert(0, first)
    elif first:
        chain.insert(0, first)
    return tuple(chain)


def decode_bytes(data: bytes, declared: str | None = None) -> Decoded:
    """严格解码；只有全部候选都失败才抛 LookupError。"""
    errors: list[str] = []
    for index, encoding in enumerate(chain_for(declared)):
        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, LookupError) as exc:  # noqa: PERF203
            errors.append(f"{encoding}: {type(exc).__name__}")
            continue
        return Decoded(
            text=text,
            encoding=encoding,
            bom_stripped=encoding == "utf-8-sig" or text.startswith("\ufeff"),
            fallback=index > 0,
            flags=(["E_BOM_STRIPPED"] if encoding == "utf-8-sig" or data[:3] == b"\xef\xbb\xbf" else []),
        )
    raise UnicodeDecodeError("utf-8", data[:16], 0, 1,
                             "回退链全部失败：" + "; ".join(errors))
