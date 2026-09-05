"""导出器基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.node import Node


def is_exportable(node: Node) -> bool:
    """检查节点是否具备对应协议导出所需的基础字段。"""

    if not node.server or not isinstance(node.port, int) or not 0 < node.port < 65536:
        return False
    if node.type in {"vless", "vmess", "tuic"}:
        return bool(node.uuid)
    if node.type == "shadowsocks":
        return bool(node.cipher and node.password)
    if node.type in {"trojan", "hysteria", "hysteria2"}:
        return bool(node.password)
    return node.type in {"socks", "http"}


class BaseExporter(ABC):
    """所有导出器接收 (Node, 展示名) 有序列表并生成订阅文本。"""

    @abstractmethod
    def export(self, items: list[tuple[Node, str]]) -> str:
        """把节点列表导出为订阅配置文本。"""


def exportable_items(items: list[tuple[Node, str]]) -> list[tuple[Node, str]]:
    """过滤不具备最小必要字段的异常节点，避免单个节点破坏整个订阅。"""

    return [(node, name) for node, name in items if is_exportable(node)]


def unique_display_names(
    items: list[tuple[Node, str]],
) -> list[tuple[Node, str]]:
    """为依赖名称引用的客户端配置生成唯一展示名。"""

    result: list[tuple[Node, str]] = []
    used: set[str] = set()
    next_suffix: dict[str, int] = {}
    for node, raw_name in items:
        base_name = str(raw_name or node.server).strip() or node.server
        name = base_name
        suffix = next_suffix.get(base_name, 1)
        while name in used:
            suffix += 1
            name = f"{base_name}-{suffix}"
        next_suffix[base_name] = suffix
        used.add(name)
        result.append((node, name))
    return result


def exportable_items_for_format(
    items: list[tuple[Node, str]], output_format: str
) -> list[tuple[Node, str]]:
    """按输出格式过滤协议，保留旧 Clash 协议并避免新格式抛出异常。"""

    supported = {
        "clash": {
            "vless", "shadowsocks", "vmess", "trojan", "socks", "http",
            "hysteria", "hysteria2", "tuic",
        },
        "mihomo": {
            "vless", "shadowsocks", "vmess", "trojan", "socks", "http",
            "hysteria", "hysteria2", "tuic",
        },
        "singbox": {"vless", "shadowsocks", "vmess", "trojan"},
        "uri": {"vless", "shadowsocks", "vmess", "trojan"},
    }
    return [
        (node, name)
        for node, name in exportable_items(items)
        if node.type in supported.get(output_format, set())
    ]
