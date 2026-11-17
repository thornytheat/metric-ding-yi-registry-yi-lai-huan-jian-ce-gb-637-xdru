"""按 \\n 切行，保留原始行号；CRLF 归一但不合并逻辑行。

不用 str.splitlines()：它会在 \\x0b、\\x0c、\\u2028、\\x85 上也切一刀，
把一条定义拆成两条（TRAP-03 的同类陷阱在 DSL 文本上的表现）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import decode


@dataclass
class RawLine:
    line_no: int
    raw: str
    crlf: bool = False


def split_lines(text: str) -> tuple[list[RawLine], int]:
    """返回行列表与 CRLF 行数；末尾换行不产生空行。"""
    if text == "":
        return [], 0
    body = text[:-1] if text.endswith("\n") else text
    parts = body.split("\n")
    rows: list[RawLine] = []
    crlf = 0
    for index, part in enumerate(parts, start=1):
        had_crlf = part.endswith("\r")
        if had_crlf:
            part = part[:-1]
            crlf += 1
        rows.append(RawLine(line_no=index, raw=part, crlf=had_crlf))
    return rows, crlf


def read_text_file(path: Path) -> bytes:
    return Path(path).read_bytes()


def read_source(sample_dir: Path, *, text: str | None = None,
                name: str | None = None) -> tuple[decode.Decoded, str]:
    """上传文本与样例文件走同一条解码路径。"""
    if text is not None:
        decoded = decode.decode_bytes(text.encode("utf-8"))
        return decoded, "upload"
    filename = name or "metrics_dirty.dsl"
    data = read_text_file(Path(sample_dir) / filename)
    return decode.decode_bytes(data), f"sample:{filename}"
