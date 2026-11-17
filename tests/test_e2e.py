"""端到端：样例 → 接入 → 诊断 → 图 → 版本 → 影响面 → 导出，含失败输入与幂等。

这是唯一一条跨模块的链路测试，断言的是账目自洽与导出可用，不重复单模块断言。
"""
from __future__ import annotations

from decimal import Decimal

from fixtures import expected as EX


def test_pipeline_from_sample_to_export(client):
    """端到端：一次样例运行走到四个导出，账目自洽。"""
    created = client.post("/api/import", json={})
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "done"
    assert body["reused"] is False
    batch_id = body["batch_id"]
    assert body["counters"]["metrics_registered"] == str(EX.LINES_REGISTERED)

    diag = client.get("/api/diagnostics").json()
    assert diag["total"] == EX.DIAG_TOTAL
    assert diag["by_level"]["error"] == 24

    graph = client.get("/api/graph").json()
    assert graph["counts"] == {"nodes": EX.NODES_TOTAL, "edges": EX.EDGES_TOTAL,
                               "components": 23, "cycles": EX.CYCLE_COMPONENTS,
                               "cycle_metrics": EX.CYCLE_METRICS}
    assert {c["size"] for c in graph["cycles"]} == {1, 2, 3}
    assert len(graph["conflicts"]) == EX.CONFLICTS

    versions = client.get("/api/versions").json()
    assert versions["counts"]["OVERLAP"] == EX.VERSION_OVERLAP
    assert versions["counts"]["INVERTED"] == EX.VERSION_INVERTED

    impact = client.get("/api/impact?metric=销售额").json()
    assert Decimal(impact["score"]) == Decimal("37.50")

    accounts = client.get("/api/reconcile").json()
    assert accounts["all_balanced"] is True
    assert accounts["details"]["lines_total"] == EX.LINES_TOTAL

    metrics_csv = client.get("/api/export/metrics.csv")
    assert metrics_csv.status_code == 200
    assert len(metrics_csv.content.decode("utf-8-sig").splitlines()) - 1 == EX.LINES_REGISTERED
    manifest = client.get("/api/export/manifest.json").json()
    assert manifest["batch_id"] == batch_id
    assert len(manifest["manifest"]["inputs"]) == 3

    for page in ("/", "/contract", "/diagnostics", "/graph", "/versions", "/impact"):
        response = client.get(page)
        assert response.status_code == 200
        assert "metricreg" in response.text


def test_failure_inputs_return_4xx(client):
    """失败输入：三种空态、未知样例、未知指标、陈旧提交。"""
    empty = client.post("/api/import", json={"text": ""})
    assert empty.status_code == 400
    assert empty.json()["error"] == "E_EMPTY_INPUT"

    blanks = client.post("/api/import", json={"text": " \n  \n"})
    assert blanks.status_code == 400
    assert blanks.json()["error"] == "E_EMPTY_BLANKS"

    comments = client.post("/api/import", json={"text": "# 只有注释\n"})
    assert comments.status_code == 400
    assert comments.json()["error"] == "E_EMPTY_COMMENTS"

    unknown_sample = client.post("/api/import", json={"sample": "not_exists.dsl"})
    assert unknown_sample.status_code == 400
    assert unknown_sample.json()["error"] == "E_EMPTY_INPUT"

    assert client.get("/api/impact?metric=没有这个指标").status_code == 404
    assert client.post("/api/import", json={}).status_code == 200
    stale = client.post("/api/versions/submit",
                        json={"metric": "销售额", "version": 1,
                              "valid_from": "2026-08-01", "valid_to": "2026-09-01"})
    assert stale.status_code == 409
    assert stale.json()["error"] == "V_STALE_SUBMIT"


def test_rerun_is_idempotent_end_to_end(client):
    """端到端幂等：两次导入返回同一批次，行数不变，批次只增一条。"""
    first = client.post("/api/import", json={}).json()
    rows_after_first = client.get("/api/batch").json()["counters"]
    second = client.post("/api/import", json={}).json()
    assert second["reused"] is True
    assert second["batch_id"] == first["batch_id"]
    rows_after_second = client.get("/api/batch").json()["counters"]
    assert rows_after_second == rows_after_first
    history = client.get("/api/batches").json()
    assert history["count"] == 1
    assert history["latest"] == first["batch_id"]
