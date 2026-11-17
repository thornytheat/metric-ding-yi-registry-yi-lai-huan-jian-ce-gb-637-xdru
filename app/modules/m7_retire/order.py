"""迁移次序：依赖方先迁，被依赖方后下线；环内与孤立节点分开。

边 A → B 表示 A 依赖 B。下线 B 之前，依赖 B 的 A 必须先改写，
所以次序是「出边指向的方向反着走」：B 的可下线时刻，取决于还有几个
依赖方没迁完。用 Kahn 从「没有依赖方」的节点开始排出确定性次序。

两处朴素实现会错：
1. 对全图排序，环内节点得不到次序就静默跳过，阻断项凭空消失；
2. 把单点分量当环（TRAP-28），孤立指标被标成环，阻断项多出一批假结果。

这里把环内指标显式排除并交给阻断表，孤立指标单列、不进次序约束。
"""
from __future__ import annotations

import heapq


def subgraph_edges(members: set[str], adj: dict[str, list[str]]) -> list[tuple[str, str]]:
    """只保留两端都在集合内的依赖边。"""
    edges: list[tuple[str, str]] = []
    for src in sorted(members):
        for dst in sorted(set(adj.get(src, []))):
            if dst in members:
                edges.append((src, dst))
    return edges


def dependents_index(members: set[str], adj: dict[str, list[str]]) -> dict[str, list[str]]:
    """被依赖方 → 依赖它的成员（集合内）。"""
    index: dict[str, list[str]] = {name: [] for name in members}
    for src, dst in subgraph_edges(members, adj):
        index[dst].append(src)
    for key in index:
        index[key] = sorted(index[key])
    return index


def retire_order(affected: set[str], adj: dict[str, list[str]],
                 blocked: set[str]) -> dict:
    """确定性迁移次序：每次取字典序最小、且已无未迁依赖方的节点。"""
    remaining = sorted(set(affected) - set(blocked))
    inside = set(remaining)
    index = dependents_index(inside, adj)
    pending = {name: len(index[name]) for name in remaining}
    ready = [name for name in remaining if pending[name] == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        for provider in sorted(set(adj.get(name, []))):
            if provider not in inside:
                continue
            pending[provider] -= 1
            if pending[provider] == 0:
                heapq.heappush(ready, provider)
    stuck = sorted(set(remaining) - set(order))
    return {
        "order": order,
        "stuck": stuck,
        "edges": len(subgraph_edges(inside, adj)),
        "blocked": sorted(set(blocked)),
        "affected": sorted(set(affected)),
    }


def singleton_components(components: list[dict]) -> list[str]:
    """单点分量清单：朴素写法把它们全当环（TRAP-28），这里只用来算偏差。"""
    return sorted(
        (component.get("members") or [""])[0]
        for component in components
        if len(component.get("members") or []) == 1
    )


def naive_ring_count(components: list[dict], adj: dict[str, list[str]]) -> int:
    """朴素写法会报出的环数：单点分量一律当环 + 每个成员按起点轮转各报一次。"""
    total = 0
    for component in components:
        members = sorted(set(component.get("members") or []))
        if not members:
            continue
        if len(members) == 1:
            total += 1
            continue
        total += len(members)
    return total


def step_rows(order: list[str], *, dependents: dict[str, list[str]],
              reports_by_metric: dict[str, list[str]]) -> list[dict]:
    """迁移清单的一行：步骤、指标、要不要先改报表。"""
    rows: list[dict] = []
    for index, name in enumerate(order, start=1):
        hits = reports_by_metric.get(name, [])
        rows.append({
            "step": index,
            "metric": name,
            "dependents": len(dependents.get(name, [])),
            "dependents_text": ",".join(dependents.get(name, [])) or "—",
            "report_count": len(hits),
            "reports_text": ",".join(hits) or "—",
        })
    return rows
