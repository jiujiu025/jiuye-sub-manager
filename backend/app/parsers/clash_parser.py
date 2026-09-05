"""Clash/Mihomo YAML 订阅解析。"""

from __future__ import annotations

import yaml

from app.parsers.base import BaseParser, ParseError, ParsedNode
from app.utils.country import detect_country

_SUPPORTED_TYPES = {"vless", "ss", "shadowsocks", "vmess", "trojan"}


def _as_bool(value: object, default: bool = False) -> bool:
    """兼容 YAML 布尔值和少数字符串布尔值。"""

    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def _transport_fields(item: dict) -> tuple[str | None, str | None, str | None]:
    """从 Clash 的 ws-opts 或旧式顶层字段提取 WebSocket 参数。"""

    ws_opts = item.get("ws-opts")
    if not isinstance(ws_opts, dict):
        ws_opts = {}
    headers = ws_opts.get("headers")
    if not isinstance(headers, dict):
        headers = item.get("ws-headers")
    if not isinstance(headers, dict):
        headers = {}
    host = next(
        (value for key, value in headers.items() if str(key).lower() == "host"),
        None,
    )
    path = ws_opts.get("path") or item.get("ws-path") or item.get("path")
    return item.get("network"), path, host or item.get("host")


def _port(value: object) -> int | None:
    """读取 Clash 端口，拒绝布尔值和非数字值。"""

    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 < parsed < 65536 else None


def _extract_node(item: dict) -> ParsedNode | None:
    raw_type = str(item.get("type", "")).lower()
    if raw_type not in _SUPPORTED_TYPES:
        return None
    node_type = "shadowsocks" if raw_type == "ss" else raw_type
    server = item.get("server")
    port = _port(item.get("port"))
    name = item.get("name") or server or ""
    if not server or port is None:
        return None
    network, path, host = _transport_fields(item)
    reality_opts = item.get("reality-opts")
    if not isinstance(reality_opts, dict):
        reality_opts = {}
    security = item.get("security")
    is_reality = node_type == "vless" and (
        str(security or "").lower() == "reality" or bool(reality_opts)
    )
    if is_reality and not security:
        security = "reality"
    security_text = str(security or "").strip().lower()
    if node_type == "vless":
        security = security_text or None
    tls_default = is_reality or node_type == "trojan"
    cipher = item.get("cipher")
    if node_type == "vmess":
        cipher = cipher or item.get("security")
    return ParsedNode(
        original_name=str(name),
        type=node_type,
        server=str(server),
        port=port,
        uuid=item.get("uuid"),
        password=item.get("password"),
        cipher=cipher,
        network=network,
        security=security,
        tls=_as_bool(item.get("tls"), tls_default)
        or security_text in {"tls", "reality"}
        or is_reality,
        sni=item.get("sni") or item.get("servername"),
        fingerprint=item.get("client-fingerprint") or item.get("fingerprint") or item.get("fp"),
        public_key=reality_opts.get("public-key") or item.get("public-key") or item.get("pbk"),
        short_id=reality_opts.get("short-id") or item.get("short-id") or item.get("sid"),
        path=path,
        host=host,
        country=detect_country(str(name)),
        metadata=item,
    )


class ClashParser(BaseParser):
    """解析 Clash YAML 中的 proxies 列表。"""

    def parse(self, content: str) -> list[ParsedNode]:
        try:
            data = yaml.safe_load(content)
        except (yaml.YAMLError, RecursionError) as exc:
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
