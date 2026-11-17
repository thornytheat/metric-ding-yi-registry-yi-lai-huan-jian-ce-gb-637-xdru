"""环最小化：一个强连通分量只出一个环。

两种朴素写法都会把环数算多（TRAP-27）：
1. 环内每个成员各报一次——3 元环报 3 个环；
2. 以每个成员为起点各走一次——同一个环按轮转报 len(成员) 次。

这里的环键定为「成员集合排序后取摘要」，一个分量只出一条；
环路径再规范轮转到字典序最小成员开头，所以起点与遍历顺序都不影响结论。

单点分量只有存在自环才算环（TRAP-28）：没有依赖边的孤立指标不入环，
单独列为“可直接下线”，否则迁移清单会凭空多出一批阻断。
"""
from __future__ import annotations

import hashlib
from collections import deque


def canonical_ring(path: list[str]) -> list[str]:
    """把闭合路径轮转到字典序最小成员开头；首尾同名，中间不重复。"""
    body = [name for name in path]
    if len(body) > 1 and body[0] == body[-1]:
        body = body[:-1]
    unique: list[str] = []
    for name in body:
        if name not in unique:
            unique.append(name)
    if not unique:
        return []
    pivot = unique.index(min(unique))
    rotated = unique[pivot:] + unique[:pivot]
    return rotated + [rotated[0]]


def shortest_ring(members: list[str], adj: dict[str, list[str]]) -> list[str]:
    """分量内回到起点的最短有向回路；单点且无自环返回空列表。"""
    group = sorted(set(members))
    if not group:
        return []
    if len(group) == 1:
        only = group[0]
        return [only, only] if only in adj.get(only, []) else []
    inside = set(group)
    start = group[0]
    parent: dict[str, str | None] = {start: None}
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        for target in sorted(set(adj.get(node, []))):
            if target not in inside:
                continue
            if target == start:
                chain: list[str] = []
                cursor: str | None = node
                while cursor is not None:
                    chain.append(cursor)
                    cursor = parent[cursor]
                chain.reverse()
                return canonical_ring(chain + [start])
            if target not in parent:
                parent[target] = node
                queue.append(target)
    return []


def ring_key(members: list[str]) -> str:
    blob = "|".join(sorted(set(members)))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10]


def rotation_count(members: list[str]) -> int:
    """朴素实现按起点轮转会重复报几次：等于成员数（单点算 1 次）。"""
    return max(1, len(set(members)))


def minimal_rings(components: list[dict], adj: dict[str, list[str]]) -> list[dict]:
    """每个环形分量一条环；同分量重复传入也只保留首条。"""
    rings: list[dict] = []
    seen: set[str] = set()
    for component in components:
        members = sorted(set(component.get("members") or []))
        if not members:
            continue
        path = shortest_ring(members, adj)
        if not path:
            continue
        key = ring_key(members)
        if key in seen:
            continue
        seen.add(key)
        rings.append({
            "ring_id": key,
            "members": members,
            "path": path,
            "size": len(members),
            "self_loop": len(members) == 1,
            "rotations": rotation_count(members),
            "head": path[0],
        })
    rings.sort(key=lambda ring: (-ring["size"], ring["ring_id"]))
    return rings


def ring_members(rings: list[dict]) -> set[str]:
    members: set[str] = set()
    for ring in rings:
        members.update(ring["members"])
    return members


def isolated_nodes(nodes: list[str], adj: dict[str, list[str]]) -> list[str]:
    """指标图里出度与入度都为 0 的节点；孤立不是环，自环也不算孤立。"""
    has_out: set[str] = set()
    has_in: set[str] = set()
    for src, targets in adj.items():
        for dst in targets:
            has_out.add(src)
            has_in.add(dst)
    return sorted({name for name in nodes} - has_out - has_in)


def partition(rings: list[dict]) -> dict:
    """环成员两两不交且并集等于各环成员数之和——分量划分不重不漏。"""
    seen: set[str] = set()
    duplicated: list[str] = []
    total = 0
    for ring in rings:
        members = set(ring["members"])
        if members & seen:
            duplicated.append(ring["ring_id"])
        seen |= members
        total += len(members)
    return {
        "ring_count": len(rings),
        "ring_members": len(seen),
        "sum_sizes": total,
        "disjoint": not duplicated,
        "duplicated": sorted(duplicated),
    }
