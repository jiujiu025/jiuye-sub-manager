"""Clash/Mihomo YAML 订阅解析。"""

from __future__ import annotations

import yaml

from app.parsers.base import BaseParser, ParseError, ParsedNode
from app.utils.country import detect_country

_SUPPORTED_TYPES = {"vless", "shadowsocks"}


def _extract_node(item: dict) -> ParsedNode | None:
    node_type = str(item.get("type", "")).lower()
    if node_type not in _SUPPORTED_TYPES:
        return None
    server = item.get("server")
    port = item.get("port")
    name = item.get("name") or server or ""
    if not server or not isinstance(port, int):
        return None
    headers = item.get("ws-headers")
    host = item.get("host")
    if isinstance(headers, dict) and not host:
        host = headers.get("Host") or headers.get("host")
    return ParsedNode(
        original_name=str(name),
        type=node_type,
        server=str(server),
        port=port,
        uuid=item.get("uuid"),
        password=item.get("password"),
        cipher=item.get("cipher"),
        network=item.get("network"),
        security=item.get("security"),
        tls=item.get("tls"),
        sni=item.get("sni") or item.get("servername"),
        fingerprint=item.get("client-fingerprint") or item.get("fp"),
        public_key=item.get("public-key") or item.get("pbk"),
        short_id=item.get("short-id") or item.get("sid"),
        path=item.get("ws-path") or item.get("path"),
        host=host,
        country=detect_country(str(name)),
        metadata=item,
    )


class ClashParser(BaseParser):
    """解析 Clash YAML 中的 proxies 列表。"""

    def parse(self, content: str) -> list[ParsedNode]:
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ParseError(f"Clash YAML 解析失败: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("proxies"), list):
            raise ParseError("Clash 配置缺少 proxies 列表")
        nodes: list[ParsedNode] = []
        for item in data["proxies"]:
            if not isinstance(item, dict):
                continue
            node = _extract_node(item)
            if node is not None:
                nodes.append(node)
        return nodes
