"""M7 下线影响与迁移顺序：环最小化、阻断项、版本含义、接口与页面。

固定样例（metrics_dirty.dsl）上的确定值：
- 环形分量 3 个，朴素按起点轮转与单点当环会数出 26 个（TRAP-27 / TRAP-28）；
- 请求台账默认目标 毛利额、销售额，受影响 7 个指标，可排序 4 个，阻断 3 个。
"""
from __future__ import annotations

from app.modules.m7_retire import service

EXPECTED_ISOLATED = {
    "中文聚合", "件单价", "全角写法", "全角分组", "别名命中", "品类销售额",
    "城市销售额", "声明多余", "大数常量", "客单价", "悬空引用", "渠道销售额",
    "订单数", "访客数", "退款率", "门店销售额",
}


def plan_for(store, settings, batch_id, targets=None):
    return service.plan_for(store, settings, batch_id, targets=targets)


def test_ring_count_is_one_per_component(run, store, settings, batch_id):
    """TRAP-27：同一环按起点轮转会报多次，这里一个分量只报一个环。"""
    payload = plan_for(store, settings, batch_id)
    counters = payload["counters"]
    assert counters["rings"] == 3
    assert counters["naive_rings"] == 26
    assert counters["singletons"] == 21
    paths = [ring["path"] for ring in payload["rings"]]
    assert ["动销率", "库存深度", "周转天数", "动销率"] in paths
    assert ["净增量", "基期销售额", "净增量"] in paths
    assert ["自比值", "自比值"] in paths
    rotations = sorted(ring["rotations"] for ring in payload["rings"])
    assert rotations == [1, 2, 3]
    assert len({ring["ring_id"] for ring in payload["rings"]}) == 3


def test_isolated_nodes_are_not_rings(run, store, settings, batch_id):
    """TRAP-28：单点分量一律当环会把 21 个孤立指标判成环。"""
    payload = plan_for(store, settings, batch_id)
    assert set(payload["isolated"]) == EXPECTED_ISOLATED
    assert len(payload["isolated"]) == 16
    single = [ring["members"] for ring in payload["rings"] if ring["size"] == 1]
    assert single == [["自比值"]]
    assert "自比值" not in payload["isolated"]
    assert not (set(payload["isolated"]) & {ring["members"][0] for ring in payload["rings"]})


def test_migration_order_puts_target_last(run, store, settings, batch_id):
    payload = plan_for(store, settings, batch_id, targets="销售额")
    assert payload["order"] == ["未声明引用", "毛利率", "销售额"]
    assert payload["checklist"][-1]["metric"] == "销售额"
    assert [row["step"] for row in payload["checklist"]] == [1, 2, 3]


def test_dependents_counted_from_who_depends_on_me(run, store, settings, batch_id):
    payload = plan_for(store, settings, batch_id, targets="销售额")
    steps = {row["metric"]: row for row in payload["checklist"]}
    assert steps["毛利率"]["dependents"] == 1
    assert steps["毛利率"]["dependents_text"] == "未声明引用"
    assert steps["未声明引用"]["dependents"] == 0
    assert steps["销售额"]["report_count"] == 1
    assert steps["销售额"]["reports_text"] == "R-01"


def test_cycle_members_blocked_with_code(run, store, settings, batch_id):
    payload = plan_for(store, settings, batch_id, targets="销售额")
    cycle_rows = [(row["code"], row["metric"]) for row in payload["blockers"]
                  if row["code"] == "R_CYCLE_BLOCKED"]
    assert cycle_rows == [("R_CYCLE_BLOCKED", "动销率"),
                          ("R_CYCLE_BLOCKED", "周转天数"),
                          ("R_CYCLE_BLOCKED", "库存深度")]
    assert payload["counters"]["affected"] == 6
    assert payload["counters"]["orderable"] == 3
    assert payload["counters"]["blocked"] == 3


def test_affected_is_split_between_order_and_blocked(run, store, settings, batch_id):
    """不变量：受影响集合 = 可排序 + 阻断，环内成员不重复出现。"""
    payload = plan_for(store, settings, batch_id)
    affected = set(payload["affected"])
    order = set(payload["order"])
    blocked = {row["metric"] for row in payload["blockers"]
               if row["code"] == "R_CYCLE_BLOCKED"}
    assert order | blocked == affected
    assert not (order & blocked)


def test_partial_replacement_lists_candidates(run, store, settings, batch_id):
    payload = plan_for(store, settings, batch_id, targets="销售额")
    row = payload["rows"][0]
    assert row["replacement"]["level"] == "partial"
    assert row["replacement"]["exact"] == []
    assert row["replacement"]["partial"] == ["中文聚合", "全角写法", "别名命中"]
    assert "R_REPLACEMENT_PARTIAL" in row["codes"]
    assert row["state"] == "review"


def test_no_replacement_blocks_target(run, store, settings, batch_id):
    payload = plan_for(store, settings, batch_id, targets="毛利额")
    row = payload["rows"][0]
    assert row["replacement"]["level"] == "none"
    assert row["state"] == "blocked"
    assert "R_NO_REPLACEMENT" in row["codes"]
    assert row["weight_sum"] == "6.50"
    assert [item["report_id"] for item in row["reports"]] == ["R-05", "R-06"]


def test_version_state_uses_eval_date(run, store, settings, batch_id):
    payload = plan_for(store, settings, batch_id)
    rows = {row["metric"]: row for row in payload["rows"]}
    sales = rows["销售额"]["version"]
    assert sales["total"] == 3
    assert sales["effective"] == 1
    assert sales["versions"] == [3]
    assert sales["flags"] == ["OVERLAP"]
    profit = rows["毛利额"]["version"]
    assert profit["effective"] == 0
    assert profit["state"] == "missing"
    assert profit["flags"] == ["INVERTED"]


def test_request_rows_dedup_and_unknown(run, store, settings, batch_id):
    payload = plan_for(store, settings, batch_id)
    rows = [(row["metric"], row["status"]) for row in payload["requests"]]
    assert rows == [("销售额", "ok"), ("毛利额", "ok"),
                    ("已下线指标", "unknown"), ("销售额", "duplicate")]
    assert payload["targets"] == ["毛利额", "销售额"]
    codes = [item["code"] for item in payload["diagnostics"]]
    assert "R_REQUEST_DUPLICATE" in codes
    assert "R_TARGET_UNKNOWN" in codes
    assert "R_REPORT_DANGLING" in codes


def test_dangling_report_kept_as_evidence(run, store, settings, batch_id):
    payload = plan_for(store, settings, batch_id)
    assert payload["dangling_reports"] == [
        {"report_id": "R-10", "report_name": "历史看板",
         "metric": "已下线指标", "weight": "0.5"}]


def test_api_retire_payload(client_with_run):
    response = client_with_run.get("/api/retire?targets=销售额")
    assert response.status_code == 200
    body = response.json()
    assert body["order"] == ["未声明引用", "毛利率", "销售额"]
    assert body["counters"]["weight_sum"] == "7.50"
    assert body["rules"]["order"] == "依赖方先迁，被依赖方后下线"
    assert body["batch_id"]


def test_api_retire_rejects_unknown_and_empty(client_with_run):
    unknown = client_with_run.get("/api/retire?targets=不存在")
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "R_TARGET_UNKNOWN"
    blank = client_with_run.get("/api/retire?targets=")
    assert blank.status_code == 400
    assert blank.json()["error"] == "R_NO_TARGETS"
    missing = client_with_run.post("/api/retire", json={})
    assert missing.status_code == 400
    assert missing.json()["error"] == "R_NO_TARGETS"


def test_api_retire_post_list_targets(client_with_run):
    response = client_with_run.post("/api/retire", json={"targets": ["毛利额"]})
    assert response.status_code == 200
    body = response.json()
    assert body["targets"] == ["毛利额"]
    assert body["checklist"][-1]["metric"] == "毛利额"


def test_order_csv_export(client_with_run):
    response = client_with_run.get("/api/retire/order.csv?targets=销售额")
    assert response.status_code == 200
    rows = response.text.lstrip("\ufeff").strip().splitlines()
    assert rows[0] == "step,metric,dependents,dependents_text,report_count,report_ids"
    assert rows[1].startswith("1,未声明引用,0,")
    assert rows[-1].startswith("3,销售额,1,")
    assert len(rows) == 4


def test_page_retire_shows_plan_and_nav(client_with_run):
    response = client_with_run.get("/retire")
    assert response.status_code == 200
    assert 'data-nav="retire"' in response.text
    assert response.text.count("data-nav=") == 7
    assert "迁移顺序" in response.text
    assert "R_CYCLE_BLOCKED" in response.text


def test_page_retire_falls_back_on_bad_target(client_with_run):
    response = client_with_run.get("/retire?targets=不存在")
    assert response.status_code == 200
    assert "R_TARGET_UNKNOWN" in response.text
    assert "毛利额" in response.text
