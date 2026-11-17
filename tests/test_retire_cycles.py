"""M7 纯规则：环最小化的键与划分、迁移次序的确定性与阻断。

这段规则不碰数据库：给节点与邻接表就算结果，所以能单独钉死
「一个分量一个环」与「孤立指标不是环」这两条（TRAP-27 / TRAP-28）。
"""
from __future__ import annotations

from app.modules.m7_retire import cycles, order


def three_ring():
    adj = {"a": ["b"], "b": ["c"], "c": ["a"]}
    return ["a", "b", "c"], adj


def test_one_ring_per_component_not_per_start():
    """TRAP-27：以每个成员为起点各走一次会报 3 个环，这里只报 1 个。"""
    members, adj = three_ring()
    rings = cycles.minimal_rings([{"members": members}], adj)
    assert len(rings) == 1
    assert rings[0]["path"] == ["a", "b", "c", "a"]
    assert rings[0]["rotations"] == 3
    assert rings[0]["ring_id"] == cycles.ring_key(members)


def test_ring_key_and_path_ignore_start_member():
    _, adj = three_ring()
    first = cycles.shortest_ring(["a", "b", "c"], adj)
    second = cycles.shortest_ring(["c", "b", "a"], adj)
    assert first == second == ["a", "b", "c", "a"]
    assert cycles.ring_key(["b", "c", "a"]) == cycles.ring_key(["a", "b", "c"])


def test_two_disjoint_rings_count_two():
    adj = {"a": ["b"], "b": ["a"], "x": ["y"], "y": ["x"]}
    rings = cycles.minimal_rings(
        [{"members": ["a", "b"]}, {"members": ["x", "y"]}], adj)
    assert len(rings) == 2
    partition = cycles.partition(rings)
    assert partition["ring_members"] == 4
    assert partition["sum_sizes"] == 4
    assert partition["disjoint"] is True


def test_duplicate_component_reports_one_ring():
    members, adj = three_ring()
    rings = cycles.minimal_rings(
        [{"members": members}, {"members": members}], adj)
    assert len(rings) == 1
    assert cycles.partition(rings)["duplicated"] == []


def test_isolated_singleton_without_self_loop_is_not_ring():
    """TRAP-28：单点分量没有自环就不是环。"""
    adj = {"a": []}
    assert cycles.shortest_ring(["a"], adj) == []
    assert cycles.minimal_rings([{"members": ["a"]}], adj) == []
    assert cycles.isolated_nodes(["a"], adj) == ["a"]


def test_self_loop_is_ring_and_not_isolated():
    adj = {"a": ["a"], "b": []}
    rings = cycles.minimal_rings([{"members": ["a"]}], adj)
    assert [ring["path"] for ring in rings] == [["a", "a"]]
    assert rings[0]["self_loop"] is True
    assert cycles.isolated_nodes(["a", "b"], adj) == ["b"]


def test_kahn_order_ignores_insertion_order():
    """不变量：同一张图换个插入顺序，迁移次序完全一样。"""
    forward = {"a1": ["base"], "a2": ["base"], "base": []}
    backward = {"base": [], "a2": ["base"], "a1": ["base"]}
    first = order.retire_order({"a1", "a2", "base"}, forward, set())
    second = order.retire_order({"base", "a2", "a1"}, backward, set())
    assert first["order"] == ["a1", "a2", "base"]
    assert first["order"] == second["order"]
    assert first["stuck"] == []


def test_stuck_reported_when_cycle_left_unblocked():
    _, adj = three_ring()
    result = order.retire_order({"a", "b", "c"}, adj, set())
    assert result["order"] == []
    assert result["stuck"] == ["a", "b", "c"]
    blocked = order.retire_order({"a", "b", "c"}, adj, {"a", "b", "c"})
    assert blocked["order"] == []
    assert blocked["stuck"] == []
    assert blocked["blocked"] == ["a", "b", "c"]


def test_naive_ring_count_uses_every_start():
    """朴素计法：环内每个成员各报一次，单点分量也算一个环。"""
    adj = {"a": ["b"], "b": ["a"], "x": []}
    components = [{"members": ["a", "b"]}, {"members": ["x"]}]
    assert order.naive_ring_count(components, adj) == 3
    assert len(cycles.minimal_rings(components, adj)) == 1
    assert order.singleton_components(components) == ["x"]
