"""套餐规则应用工具：重命名、排序、编号。"""

from __future__ import annotations

from typing import Any, Protocol

from app.utils.country import COUNTRY_ABBR


class RuleNode(Protocol):
    """规则应用只需要节点上的少量展示字段。"""

    source_name: str
    type: str
    country: str | None
    name: str


def apply_rename_rules(name: str, rules: list[dict[str, Any]]) -> str:
    """按规则执行前缀/后缀/关键词替换/国家缩写。"""

    renamed = name
    for rule in rules:
        prefix = str(rule.get("prefix", ""))
        suffix = str(rule.get("suffix", ""))
        renamed = f"{prefix}{renamed}{suffix}"
        for item in rule.get("replacements", []):
            if isinstance(item, dict) and item.get("from") is not None:
                renamed = renamed.replace(
                    str(item["from"]), str(item.get("to", ""))
                )
        if rule.get("country_abbr"):
            for country, abbr in COUNTRY_ABBR.items():
                renamed = renamed.replace(country, abbr)
    return " ".join(renamed.split()) or name


def _sort_key(node: RuleNode, rule: dict[str, Any]) -> tuple[int, str]:
    """生成排序键；自定义顺序中未命中的项排最后。"""

    field = str(rule.get("field", "name"))
    order = rule.get("order") or []
    if field == "source":
        value = node.source_name
    elif field == "type":
        value = node.type
    elif field == "country":
        value = node.country or ""
    else:
        value = node.name
    if order:
        try:
            index = order.index(value)
        except ValueError:
            index = len(order)
        return (index, value)
    return (0, value)


def apply_sort_rules(
    nodes: list[RuleNode], rules: list[dict[str, Any]]
) -> None:
    """多条排序规则从后往前应用，使第一条规则优先级最高。"""

    for rule in reversed(rules):
        reverse = str(rule.get("direction", "asc")).lower() == "desc"
        nodes.sort(key=lambda node: _sort_key(node, rule), reverse=reverse)


def apply_numbering(
    nodes: list[RuleNode], rules: list[dict[str, Any]]
) -> None:
    """编号规则：按国家/来源分组生成 HK-01、JP-02 形式的名称。"""

    for rule in rules:
        if not rule.get("numbered"):
            continue
        prefix = str(rule.get("prefix", ""))
        suffix = str(rule.get("suffix", ""))
        groups: dict[str, list[RuleNode]] = {}
        for node in nodes:
            groups.setdefault(node.country or node.source_name, []).append(node)
        for key, group in groups.items():
            label = (prefix or COUNTRY_ABBR.get(key, key)).rstrip("-")
            for index, node in enumerate(group, start=1):
                node.name = f"{label}-{index:02d}{suffix}"
        break
