"""字段与聚合的登记表访问：登记名、历史别名、维度判定、冲突等级。

字段改名（TRAP-17）只在这里收口：别名表命中即视为同一字段，
不允许各处自己写 if old_name == ...。
"""
from __future__ import annotations

from ... import config

_FIELD_ALIASES: dict[str, str] = {}
for _canonical, _meta in config.FIELD_REGISTRY.items():
    _FIELD_ALIASES[_canonical.lower()] = _canonical
    for _alias in _meta["aliases"]:
        _FIELD_ALIASES[str(_alias).lower()] = _canonical


def resolve_field(name: str | None) -> str | None:
    if not name:
        return None
    return _FIELD_ALIASES.get(str(name).strip().lower())


def field_meta(name: str | None) -> dict:
    canonical = resolve_field(name)
    if canonical is None:
        return {}
    return {"name": canonical, **config.FIELD_REGISTRY[canonical]}


def is_dimension(name: str | None) -> bool:
    return resolve_field(name) in config.DIMENSIONS


def canonical_agg(name: str | None) -> str | None:
    if not name:
        return None
    raw = str(name).strip()
    upper = raw.upper()
    if upper in config.AGGREGATORS:
        return upper
    return config.AGG_ALIASES.get(raw)


def conflict_level(diff_kinds: list[str]) -> str:
    """聚合方式不同 → 阻断；仅过滤不同 → 复核；其余 → 记录。"""
    kinds = set(diff_kinds)
    if "aggregators" in kinds:
        return "BLOCK"
    if kinds & {"where", "depends", "expr"}:
        return "REVIEW"
    return "INFO"


def describe(settings) -> dict:
    return {
        "rule_version": settings.rule_version,
        "aggregators": [
            {"name": name, "return_type": spec[0], "label": spec[1],
             "aliases": sorted(a for a, v in config.AGG_ALIASES.items() if v == name)}
            for name, spec in config.AGGREGATORS.items()
        ],
        "fields": [
            {"name": name, "type": meta["type"], "unit": meta["unit"],
             "aliases": list(meta["aliases"]),
             "dimension": name in config.DIMENSIONS}
            for name, meta in config.FIELD_REGISTRY.items()
        ],
        "dimensions": list(config.DIMENSIONS),
        "sentinels": sorted(config.SENTINELS),
        "diag_order": list(config.DIAG_ORDER),
        "conflict_levels": [
            {"level": key, "label": label, "meaning": meaning}
            for key, label, meaning in config.CONFLICT_LEVELS
        ],
        "version_window": "[valid_from, valid_to) 半开区间，valid_to 留空表示未关闭",
        "expression_ops": {"+": 1, "-": 1, "*": 2, "/": 2},
        "grammar": [
            "name = expr",
            "expr := term (('+'|'-') term)*    term := factor (('*'|'/') factor)*",
            "factor := agg '(' field ')' | ref '(' name ')' | number | '(' expr ')'",
            "clause := 'where' field '=' value | 'group' 'by' dim (',' dim)* "
            "| 'depends' ':' name (',' name)*",
        ],
    }
