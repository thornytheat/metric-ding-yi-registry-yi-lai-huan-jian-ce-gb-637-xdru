"""M5 版本区间与批次：半开区间、重叠、倒挂、陈旧提交、批次历史。

对应 TRAP-25（版本生效区间重叠）、TRAP-26（陈旧提交覆盖新数据）。
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.errors import BadRequest, Conflict, NotFound
from app.modules.m5_versions import batches, intervals, service, stale
from fixtures import expected as EX


def test_overlap_flagged(run, store):
    """TRAP-25：[01-01,04-01) 与 [03-15,07-01) 同时生效必须标出来。"""
    rows = store.load_versions(run["batch"]["batch_id"])
    sales = [r for r in rows if r["metric"] == "销售额"]
    assert [r["status"] for r in sales] == ["OVERLAP", "OVERLAP", "OK"]
    assert len(rows) == EX.VERSION_ROWS
    overlap = [r for r in rows if r["status"] == "OVERLAP"]
    assert len(overlap) == EX.VERSION_OVERLAP

    diags = store.load_diagnostics(run["batch"]["batch_id"])
    codes = [d["code"] for d in diags if d["stage"] == "version"]
    assert codes.count("V_INTERVAL_OVERLAP") == 1
    assert codes.count("V_INTERVAL_INVERTED") == 1


def test_adjacent_intervals_do_not_overlap():
    """半开区间：前者到 07-01 结束，后者 07-01 开始，不算重叠。"""
    first = {"valid_from": "2026-04-01", "valid_to": "2026-07-01"}
    second = {"valid_from": "2026-07-01", "valid_to": "9999-12-31"}
    assert intervals.overlaps(first, second) is False
    assert intervals.covers(second, dt.date(2026, 7, 1)) is True
    assert intervals.covers(first, dt.date(2026, 7, 1)) is False
    assert intervals.covers(first, dt.date(2026, 4, 1)) is True
    assert intervals.covers(first, dt.date(2026, 3, 31)) is False


def test_inverted_interval_flagged(run, store):
    rows = store.load_versions(run["batch"]["batch_id"])
    inverted = [r for r in rows if r["status"] == "INVERTED"]
    assert len(inverted) == EX.VERSION_INVERTED
    assert inverted[0]["metric"] == "毛利额"
    assert inverted[0]["valid_to"] == "2026-02-01"
    unknown = [r for r in rows if r["status"] == "UNKNOWN"]
    assert [r["metric"] for r in unknown] == ["已下线指标"]


def test_stale_submit_rejected(run, store, client_with_run):
    """TRAP-26：提交版本不晚于库中最新值，返回 409 并保留原台账。"""
    batch = store.get_batch(run["batch"]["batch_id"])
    with pytest.raises(Conflict) as exc:
        stale.submit(store, batch, {"metric": "销售额", "version": 2,
                                    "valid_from": "2026-08-01",
                                    "valid_to": "2026-09-01"})
    payload = exc.value.payload()
    assert payload["error"] == "V_STALE_SUBMIT"
    assert payload["detail"]["current"] == 3
    assert payload["detail"]["submitted"] == 2

    response = client_with_run.post("/api/versions/submit",
                                    json={"metric": "销售额", "version": 2,
                                          "valid_from": "2026-08-01",
                                          "valid_to": "2026-09-01"})
    assert response.status_code == 409
    assert response.json()["error"] == "V_STALE_SUBMIT"
    rows = store.load_versions(run["batch"]["batch_id"])
    assert len(rows) == EX.VERSION_ROWS


def test_newer_submit_accepted(run, store, client_with_run):
    response = client_with_run.post("/api/versions/submit",
                                    json={"metric": "毛利额", "version": 3,
                                          "valid_from": "2026-06-01",
                                          "valid_to": "2026-07-01"})
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["version"] == 3
    assert body["previous"] == 2
    assert body["overlapped"] == []
    rows = store.load_versions(run["batch"]["batch_id"])
    assert len(rows) == EX.VERSION_ROWS + 1
    newest = [r for r in rows if r["metric"] == "毛利额" and r["version"] == 3][0]
    assert newest["status"] == "OK"


def test_submit_validation_errors(run, store):
    batch = store.get_batch(run["batch"]["batch_id"])
    with pytest.raises(NotFound):
        stale.submit(store, batch, {"metric": "不存在的指标", "version": 9,
                                    "valid_from": "2026-08-01"})
    with pytest.raises(BadRequest) as bad_date:
        stale.submit(store, batch, {"metric": "销售额", "version": 9,
                                    "valid_from": "不是日期"})
    assert bad_date.value.payload()["error"] == "V_INTERVAL_INVERTED"
    with pytest.raises(BadRequest) as inverted:
        stale.submit(store, batch, {"metric": "销售额", "version": 9,
                                    "valid_from": "2026-08-01",
                                    "valid_to": "2026-07-01"})
    assert inverted.value.payload()["error"] == "V_INTERVAL_INVERTED"


def test_parse_versions_text_keeps_open_end():
    parsed = intervals.parse_versions_text(
        "metric,version,valid_from,valid_to,author,submitted_at\n"
        "客单价,1,2026-01-01,,wangq,2026-01-03\n")
    row = parsed["rows"][0]
    assert row["valid_to"] == "9999-12-31"
    assert row["valid_to_text"] == ""
    assert parsed["diagnostics"] == []
    view = service.view(parsed["rows"])
    assert view["total"] == 1
    assert view["counts"] == {"OK": 1}


def test_batches_history_uses_manifest(run, store):
    rows = batches.history(store)
    assert len(rows) == 1
    row = rows[0]
    assert row["batch_id"] == run["batch"]["batch_id"]
    assert row["lines"] == str(EX.LINES_TOTAL)
    assert row["registered"] == str(EX.LINES_REGISTERED)
    assert row["isolated"] == str(EX.LINES_ISOLATED)
    assert len(row["inputs"]) == 3
    assert row["status"] == "done"
    assert batches.replay_note(True) == "输入摘要命中已完成批次，复用结果"
    assert batches.replay_note(False) == ""


def test_cover_boundary_excludes_valid_to():
    """边界：半开区间 [valid_from, valid_to)，valid_to 当天已经不属于该版本。"""
    row = {"valid_from": "2026-01-01", "valid_to": "2026-04-01"}
    assert intervals.covers(row, dt.date(2026, 1, 1)) is True
    assert intervals.covers(row, dt.date(2026, 3, 31)) is True
    assert intervals.covers(row, dt.date(2026, 4, 1)) is False
    assert intervals.covers(row, dt.date(2025, 12, 31)) is False


def test_open_end_version_covers_far_future():
    """边界：valid_to 留空用 9999-12-31 参与比较，远期日期仍生效。"""
    row = {"valid_from": "2026-01-01", "valid_to": "9999-12-31"}
    assert intervals.covers(row, dt.date(2026, 11, 15)) is True
    assert intervals.covers(row, dt.date(2030, 1, 1)) is True
