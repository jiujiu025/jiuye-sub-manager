"""常见 V2Ray JSON 配置解析。"""

from __future__ import annotations

import json
from copy import deepcopy

from app.parsers.base import BaseParser, ParseError, ParsedNode
from app.utils.country import detect_country


def _port(value: object) -> int:
    """解析 V2Ray 配置中的数字或字符串端口。"""

    if isinstance(value, bool):
        raise ParseError("V2Ray 节点端口无效")
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ParseError("V2Ray 节点端口无效") from exc
    if not 0 < port < 65536:
        raise ParseError("V2Ray 节点端口超出范围")
    return port


def _first_value(*values: object) -> object | None:
    """返回第一个非空配置值。"""

    for value in values:
        if value not in (None, ""):
            return value
    return None


def _as_list(value: object) -> list:
    """兼容 V2Ray 配置中单对象和数组两种写法。"""

    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _header_value(headers: object, name: str) -> object | None:
    """大小写不敏感读取传输层 Header。"""

    if not isinstance(headers, dict):
        return None
    expected = name.lower()
    return next(
        (value for key, value in headers.items() if str(key).lower() == expected),
        None,
    )


def _stream_fields(outbound: dict) -> dict:
    """提取 V2Ray TLS、Reality 和 WebSocket 的通用字段。"""

    stream = outbound.get("streamSettings") or outbound.get("stream_settings") or {}
    if not isinstance(stream, dict):
        stream = {}
    network = str(stream.get("network") or "tcp").lower()
    security = str(stream.get("security") or "none").lower()
    tls_settings = stream.get("tlsSettings") or stream.get("tls_settings") or {}
    reality_settings = (
        stream.get("realitySettings") or stream.get("reality_settings") or {}
    )
    if not isinstance(tls_settings, dict):
        tls_settings = {}
    if not isinstance(reality_settings, dict):
        reality_settings = {}
    ws_settings = stream.get("wsSettings") or stream.get("ws_settings") or {}
    if not isinstance(ws_settings, dict):
        ws_settings = {}
    headers = ws_settings.get("headers") or {}
    sni = _first_value(
        tls_settings.get("serverName"),
        tls_settings.get("server_name"),
        reality_settings.get("serverName"),
        reality_settings.get("server_name"),
    )
    fingerprint = _first_value(
        reality_settings.get("fingerprint"),
        tls_settings.get("fingerprint"),
    )
    public_key = _first_value(
        reality_settings.get("publicKey"),
        reality_settings.get("public-key"),
        reality_settings.get("pbk"),
    )
    short_id = _first_value(
        reality_settings.get("shortId"),
        reality_settings.get("short-id"),
        reality_settings.get("sid"),
    )
    return {
        "network": network,
        "security": security if security != "none" else None,
        "tls": security in {"tls", "reality"},
        "sni": sni,
        "fingerprint": fingerprint,
        "public_key": public_key,
        "short_id": short_id,
        "path": ws_settings.get("path"),
        "host": _header_value(headers, "host"),
        "stream": stream,
    }


def _parse_vnext(outbound: dict, protocol: str) -> list[ParsedNode]:
    settings = outbound.get("settings") or {}
    if not isinstance(settings, dict):
        return []
    vnext = _as_list(settings.get("vnext"))
    fields = _stream_fields(outbound)
    result: list[ParsedNode] = []
    for item in vnext:
        if not isinstance(item, dict):
            continue
        server = item.get("address") or item.get("server")
        port = item.get("port")
        users = item.get("users") or []
        if not server or not port or not users:
            continue
        for user in _as_list(users):
            if not isinstance(user, dict):
                continue
            uuid = user.get("id") or user.get("uuid")
            if not uuid:
                continue
            name = str(outbound.get("tag") or server)
            metadata = deepcopy(outbound)
            metadata["streamSettings"] = fields["stream"]
            if user.get("alterId") is not None:
                metadata["aid"] = user.get("alterId")
            if user.get("flow"):
                metadata["flow"] = user.get("flow")
            result.append(
                ParsedNode(
                    original_name=name,
                    type=protocol,
                    server=str(server),
                    port=_port(port),
                    uuid=str(uuid),
                    cipher=str(user.get("security") or "auto") if protocol == "vmess" else None,
                    network=fields["network"],
                    security=fields["security"],
                    tls=fields["tls"],
                    sni=fields["sni"],
                    fingerprint=fields["fingerprint"],
                    public_key=fields["public_key"],
                    short_id=fields["short_id"],
                    path=fields["path"],
                    host=fields["host"],
                    country=detect_country(name),
                    metadata=metadata,
                )
            )
    return result


def _parse_servers(outbound: dict, protocol: str) -> list[ParsedNode]:
    """兼容 V2Ray shadowsocks/trojan 的 servers 配置。"""

    settings = outbound.get("settings") or {}
    if not isinstance(settings, dict):
        return []
    fields = _stream_fields(outbound)
    result: list[ParsedNode] = []
    for item in _as_list(settings.get("servers")):
        if not isinstance(item, dict):
            continue
        server = item.get("address") or item.get("server")
        port = item.get("port")
        password = item.get("password")
        if not server or not port or not password:
            continue
        name = str(outbound.get("tag") or server)
        result.append(
            ParsedNode(
                original_name=name,
                type="shadowsocks" if protocol == "shadowsocks" else "trojan",
                server=str(server),
                port=_port(port),
                password=str(password),
                cipher=item.get("method") if protocol == "shadowsocks" else None,
                network=fields["network"],
                security=fields["security"],
                tls=fields["tls"] or protocol == "trojan",
                sni=fields["sni"],
                fingerprint=fields["fingerprint"],
                path=fields["path"],
                host=fields["host"],
                country=detect_country(name),
                metadata=deepcopy(outbound),
            )
        )
    return result


class V2RayJsonParser(BaseParser):
    """解析 V2Ray outbounds.vnext 常见配置。"""

    def parse(self, content: str) -> list[ParsedNode]:
        try:
            data = json.loads(content.lstrip("\ufeff"))
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ParseError(f"V2Ray JSON 解析失败: {exc}") from exc
        if not isinstance(data, dict):
            raise ParseError("V2Ray 配置必须是对象")
        outbounds = data.get("outbounds")
        if outbounds is None and data.get("protocol"):
            outbounds = [data]
        outbounds = _as_list(outbounds)
        if not outbounds:
            raise ParseError("V2Ray 配置缺少 outbounds 列表")
        nodes: list[ParsedNode] = []
        for outbound in outbounds:
            if not isinstance(outbound, dict):
                continue
            protocol = str(outbound.get("protocol") or "").lower()
            if protocol in {"vmess", "vless"}:
                nodes.extend(_parse_vnext(outbound, protocol))
            elif protocol in {"shadowsocks", "trojan"}:
                nodes.extend(_parse_servers(outbound, protocol))
        if not nodes:
            raise ParseError("V2Ray 配置未解析到有效节点")
        return nodes
