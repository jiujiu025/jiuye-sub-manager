"""Sing-box JSON 配置解析。"""

from __future__ import annotations

import json

from app.parsers.base import BaseParser, ParseError, ParsedNode
from app.utils.country import detect_country


def _from_outbound(item: dict) -> ParsedNode | None:
    outbound_type = str(item.get("type", "")).lower()
    server = item.get("server")
    port = item.get("server_port")
    tag = item.get("tag") or server or ""
    if not server or not port:
        return None
    raw_tls = item.get("tls")
    if raw_tls is None:
        tls_config = {}
    elif isinstance(raw_tls, bool):
        # 兼容旧版 sing-box 使用布尔值表示 TLS 开关的配置。
        tls_config = {"enabled": raw_tls}
    elif isinstance(raw_tls, dict):
        tls_config = raw_tls
    else:
        raise ParseError("Sing-box TLS 配置格式无效")
    tls_enabled = bool(tls_config.get("enabled"))
    reality = tls_config.get("reality") or {}
    if not isinstance(reality, dict):
        raise ParseError("Sing-box Reality 配置格式无效")
    utls = tls_config.get("utls") or {}
    if not isinstance(utls, dict):
        raise ParseError("Sing-box uTLS 配置格式无效")
    transport = item.get("transport")
    if transport is None:
        transport = {}
    if not isinstance(transport, dict):
        raise ParseError("Sing-box transport 配置格式无效")
    transport_headers = transport.get("headers") or {}
    if not isinstance(transport_headers, dict):
        raise ParseError("Sing-box transport.headers 配置格式无效")
    try:
        parsed_port = int(port)
    except (TypeError, ValueError) as exc:
        raise ParseError("Sing-box 节点端口无效") from exc
    if not 0 < parsed_port < 65536:
        raise ParseError("Sing-box 节点端口超出范围")
    common = {
        "original_name": str(tag),
        "server": str(server),
        "port": parsed_port,
        "tls": tls_enabled,
        "sni": tls_config.get("server_name"),
        "fingerprint": utls.get("fingerprint") or tls_config.get("fingerprint"),
        "public_key": reality.get("public_key"),
        "short_id": reality.get("short_id"),
        "country": detect_country(str(tag)),
        "metadata": item,
    }
    if outbound_type == "vless":
        return ParsedNode(
            **common,
            type="vless",
            uuid=item.get("uuid"),
            network=transport.get("type") or item.get("network"),
            path=transport.get("path"),
            host=transport_headers.get("Host"),
        )
    if outbound_type == "vmess":
        return ParsedNode(
            **common,
            type="vmess",
            uuid=item.get("uuid"),
            cipher=item.get("security") or "auto",
            network=transport.get("type"),
            path=transport.get("path"),
            host=transport_headers.get("Host"),
        )
    if outbound_type == "shadowsocks":
        return ParsedNode(
            **common,
            type="shadowsocks",
            password=item.get("password"),
            cipher=item.get("method"),
        )
    if outbound_type == "trojan":
        return ParsedNode(
            **common,
            type="trojan",
            password=item.get("password"),
            network=transport.get("type"),
        )
    if outbound_type in ("socks", "http"):
        return ParsedNode(
            **common,
            type=outbound_type,
            username=item.get("username"),
            password=item.get("password"),
        )
    if outbound_type == "hysteria2":
        return ParsedNode(
            **common,
            type="hysteria2",
            password=item.get("password"),
            network="udp",
        )
    if outbound_type == "tuic":
        return ParsedNode(
            **common,
            type="tuic",
            uuid=item.get("uuid"),
            password=item.get("password"),
        )
    return None


class SingboxParser(BaseParser):
    """解析 Sing-box JSON 的 outbounds 列表。"""

    def parse(self, content: str) -> list[ParsedNode]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ParseError(f"Sing-box JSON 解析失败: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("outbounds"), list):
            raise ParseError("Sing-box 配置缺少 outbounds 列表")
        nodes: list[ParsedNode] = []
        for item in data["outbounds"]:
            if not isinstance(item, dict):
                continue
            node = _from_outbound(item)
            if node is not None:
                nodes.append(node)
        return nodes
