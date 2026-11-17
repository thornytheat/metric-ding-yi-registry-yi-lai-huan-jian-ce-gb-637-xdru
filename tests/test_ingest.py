"""M1 指标接入：BOM、换行、编码回退、空态三态、幂等。

对应 TRAP-02（BOM 进首列名）与空态三态；反例是 `str.splitlines()`。
"""
from __future__ import annotations

import pytest

from app import config
from app.errors import BadRequest
from app.modules.m1_ingest import decode, lines, reader, service
from fixtures import expected as EX

from conftest import CLEAN, DIRTY, sample_bytes


def test_bom_stripped_before_first_name(settings, store):
    """TRAP-02：样例文件带 BOM，首个指标名必须干净。"""
    raw = sample_bytes(DIRTY)
    assert raw[:3] == b"\xef\xbb\xbf"
    decoded = decode.decode_bytes(raw)
    assert decoded.encoding == "utf-8-sig"
    assert decoded.bom_stripped is True
    assert "\ufeff" not in decoded.text

    result = service.run(settings, store)
    names = [m["name"] for m in store.load_metrics(result["batch"]["batch_id"])]
    assert names[0] == "销售额"
    assert not any(name.startswith("\ufeff") for name in names)


def test_crlf_and_lf_mixed_keep_logical_lines():
    """CRLF 与 LF 混用只归一，不合并、不拆分逻辑行。"""
    raw_rows, crlf = reader.split_lines("a=1\r\nb=2\nc=3\n")
    assert [row.line_no for row in raw_rows] == [1, 2, 3]
    assert [row.raw for row in raw_rows] == ["a=1", "b=2", "c=3"]
    assert crlf == 1

    rows, crlf_all = reader.split_lines(sample_bytes(DIRTY).decode("utf-8-sig"))
    assert len(rows) == EX.LINES_TOTAL
    assert crlf_all == 5


def test_naive_splitlines_splits_u2028(dirty_text):
    """反例：`str.splitlines()` 在 U+2028 上多切一刀，逻辑行数会变多。"""
    naive = len(dirty_text.splitlines())
    ours = len(reader.split_lines(dirty_text)[0])
    assert "\u2028" in dirty_text
    assert naive > ours
    assert naive - ours == 1


def test_empty_input_three_states(settings, store):
    """0 字符、只有空行、只有注释返回三个不同原因码。"""
    with pytest.raises(BadRequest) as empty:
        service.run(settings, store, text="")
    assert empty.value.payload()["error"] == "E_EMPTY_INPUT"

    with pytest.raises(BadRequest) as blanks:
        service.run(settings, store, text="  \n \n")
    assert blanks.value.payload()["error"] == "E_EMPTY_BLANKS"

    with pytest.raises(BadRequest) as comments:
        service.run(settings, store, text="# 只有注释\n# 没有定义\n")
    assert comments.value.payload()["error"] == "E_EMPTY_COMMENTS"


def test_idempotent_rerun_adds_no_rows(settings, store):
    """不变量：同一输入摘要重跑命中批次键，不新增行也不新增批次。"""
    first = service.run(settings, store)
    rows_before = store.count_rows(first["batch"]["batch_id"])
    batches_before = store.count_batches()

    second = service.run(settings, store)
    assert second["reused"] is True
    assert second["batch"]["batch_id"] == first["batch"]["batch_id"]
    assert store.count_batches() == batches_before
    assert store.count_rows(first["batch"]["batch_id"]) == rows_before


def test_charset_fallback_to_gb18030():
    """声明 utf-8 但字节是 gb18030 时按回退链解出中文。"""
    text = "销售额 = SUM(order_amt)\n渠道销售额 = SUM(order_amt) group by channel\n"
    decoded = decode.decode_bytes(text.encode("gb18030"))
    assert decoded.fallback is True
    assert "销售额" in decoded.text
    assert decoded.encoding == "gb18030"


def test_line_kinds_and_summary(dirty_text):
    rows, _ = reader.split_lines(dirty_text)
    summary = lines.summarize(rows)
    assert summary["total"] == EX.LINES_TOTAL
    assert summary["blank"] == EX.BLANK_LINES
    assert summary["comment"] == EX.COMMENT_LINES
    assert summary["definition"] == EX.LINES_REGISTERED + EX.LINES_ISOLATED
    assert lines.empty_state(summary) is None
    assert lines.classify("   ") == "blank"
    assert lines.classify("  # 说明") == "comment"
    assert lines.classify("销售额 = SUM(order_amt)") == "definition"


def test_clean_sample_uses_same_path(clean_run):
    """干净样例走同一条链路：8 条定义全部注册，定义本身没有任何检出。"""
    assert clean_run["counters"]["metrics_registered"] == "8"
    assert clean_run["counters"]["lines_isolated"] == "0"
    codes = {d["code"] for d in clean_run["diagnostics"]}
    assert not any(code.startswith(("Q_", "G_", "C_")) for code in codes)
    assert codes == {"V_INTERVAL_OVERLAP", "V_INTERVAL_INVERTED"}


def test_manifest_records_run_and_digest(run, store):
    batch = run["batch"]
    manifest = store.load_manifest(batch["batch_id"])
    assert manifest["run_id"] == batch["run_id"]
    assert manifest["rule_version"] == config.RULE_VERSION
    assert manifest["batch_key"] == batch["batch_key"]
    digests = {item["name"]: item["sha256"] for item in manifest["inputs"]}
    assert digests["sample:" + DIRTY] == manifest["inputs"][0]["sha256"]
    assert len(digests) == 3
    assert all(len(value) == 64 for value in digests.values())
