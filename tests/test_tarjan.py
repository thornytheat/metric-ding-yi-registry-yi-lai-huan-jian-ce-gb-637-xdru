"""M4 环检测算法：迭代 Tarjan 正确性、长链不爆栈、分量划分守恒。

对应 TRAP-20（依赖环：递归/拓扑排序直接爆栈）。
"""
from __future__ import annotations

import sys

from app.modules.m4_graph import tarjan


def test_long_ring_without_recursion_limit():
    """反例：1200 个指标首尾成环，递归实现会撞 Python 递归上限。

    TRAP-20：朴素递归 DFS 在 1200 层时抛 RecursionError，迭代版正常给出 1 个分量。
    """
    size = 1200
    assert size > sys.getrecursionlimit() - 100
    nodes = [f"m{index:04d}" for index in range(size)]
    adj = {node: [nodes[(index + 1) % size]] for index, node in enumerate(nodes)}
    components = tarjan.strongly_connected(nodes, adj)
    assert len(components) == 1
    assert len(components[0]) == size
    assert tarjan.is_cycle(components[0], adj) is True
    path = tarjan.cycle_path(components[0], adj)
    assert path[0] == path[-1] == "m0000"
    assert len(path) == size + 1


def test_component_partition_is_total():
    """不变量：分量成员是节点集合的一个划分，不重不漏。"""
    nodes = ["a", "b", "c", "d", "e", "f"]
    adj = {"a": ["b"], "b": ["a", "c"], "c": [], "d": ["d"], "e": ["f"], "f": []}
    components = tarjan.strongly_connected(nodes, adj)
    flat = [member for comp in components for member in comp]
    assert sorted(flat) == sorted(nodes)
    assert len(flat) == len(set(flat))


def test_self_loop_is_cycle():
    adj = {"自比值": ["自比值"]}
    components = tarjan.strongly_connected(["自比值"], adj)
    assert components == [["自比值"]]
    assert tarjan.is_cycle(components[0], adj) is True
    assert tarjan.cycle_path(components[0], adj) == ["自比值", "自比值"]


def test_cycle_path_starts_at_smallest():
    adj = {"b": ["c"], "c": ["a"], "a": ["b"]}
    components = tarjan.strongly_connected(["a", "b", "c"], adj)
    assert components == [["a", "b", "c"]]
    path = tarjan.cycle_path(components[0], adj)
    assert path[0] == "a" and path[-1] == "a"
    assert len(path) == 4


def test_disconnected_graph_components():
    adj = {"x": ["y"], "y": [], "z": ["z"]}
    components = tarjan.strongly_connected(["x", "y", "z"], adj)
    assert [comp for comp in components if len(comp) > 1] == []
    assert len(components) == 3
    assert tarjan.is_cycle(["y"], adj) is False


def test_empty_graph_returns_empty():
    assert tarjan.strongly_connected([], {}) == []
    assert tarjan.is_cycle([], {}) is False
