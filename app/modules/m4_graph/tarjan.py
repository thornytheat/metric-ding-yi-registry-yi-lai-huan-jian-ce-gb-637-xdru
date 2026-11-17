"""Tarjan 强连通分量：显式栈迭代实现，不用递归。

递归版在一条 1200 个指标的长依赖链上会直接撞 Python 递归上限
（TRAP-20 的爆栈分支），迭代版没有这个上限，也不依赖 sys.setrecursionlimit。
"""
from __future__ import annotations

from collections import deque


def strongly_connected(nodes: list[str], adj: dict[str, list[str]]) -> list[list[str]]:
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    ordered_nodes = list(nodes)
    for node in adj:
        if node not in ordered_nodes:
            ordered_nodes.append(node)

    for root in ordered_nodes:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, cursor = work[-1]
            succ = adj.get(node, [])
            if cursor < len(succ):
                work[-1] = (node, cursor + 1)
                target = succ[cursor]
                if target not in index:
                    index[target] = low[target] = counter
                    counter += 1
                    stack.append(target)
                    on_stack.add(target)
                    work.append((target, 0))
                elif target in on_stack:
                    low[node] = min(low[node], index[target])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                members: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    members.append(member)
                    if member == node:
                        break
                result.append(sorted(members))
    return sorted(result, key=lambda comp: (-len(comp), comp[0]))


def is_cycle(comp: list[str], adj: dict[str, list[str]]) -> bool:
    if not comp:
        return False
    if len(comp) > 1:
        return True
    only = comp[0]
    return only in adj.get(only, [])


def cycle_path(comp: list[str], adj: dict[str, list[str]]) -> list[str]:
    """在分量内找一条回到起点的最短环路，起点取字典序最小成员。"""
    members = set(comp)
    start = min(comp)
    queue = deque([start])
    parent: dict[str, str | None] = {start: None}
    while queue:
        node = queue.popleft()
        for target in adj.get(node, []):
            if target not in members:
                continue
            if target == start:
                chain: list[str] = []
                cursor: str | None = node
                while cursor is not None:
                    chain.append(cursor)
                    cursor = parent[cursor]
                chain.reverse()
                return chain + [start]
            if target not in parent:
                parent[target] = node
                queue.append(target)
    return [start, start]
