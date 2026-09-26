"""VMess URI 解析。"""

from __future__ import annotations

import json
from urllib.parse import unquote

from app.parsers.base import ParseError, ParsedNode
from app.parsers.detector import decode_base64
from app.utils.country import detect_country


def _parse_port(value: object) -> int:
    """兼容 V2Ray JSON 中常见的字符串端口，并统一校验范围。"""

    if isinstance(value, bool):
        raise ParseError("VMess 配置端口无效")
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ParseError("VMess 配置端口无效") from exc
    if not 0 < port < 65536:
        raise ParseError("VMess 配置端口超出范围")
    return port


def _as_bool(value: object) -> bool:
    """兼容 V2Ray 分享链接中的字符串布尔值。"""

    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "on", "tls"}


def parse_vmess_uri(uri: str) -> ParsedNode:
    """把 vmess://base64(JSON) 链接解析为 ParsedNode。"""

    if not uri.startswith("vmess://"):
        raise ParseError("不是有效的 VMess 链接")
    payload = unquote(uri.removeprefix("vmess://").strip())
    decoded = decode_base64(payload)
    if decoded is None:
        raise ParseError("VMess 链接 Base64 解码失败")
    try:
        data = json.loads(decoded.lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        raise ParseError("VMess 配置 JSON 无效") from exc
    if not isinstance(data, dict):
        raise ParseError("VMess 配置 JSON 必须是对象")
    server = data.get("add") or data.get("server") or data.get("address")
    port = data.get("port") or data.get("server_port")
    if not server or not port:
        raise ParseError("VMess 配置缺少服务器或端口")
    raw_uuid = data.get("id") or data.get("uuid")
    if not raw_uuid:
        raise ParseError("VMess 配置缺少 UUID")
    name = str(data.get("ps") or server)
    network = str(data.get("net") or data.get("network") or "").strip().lower()
    if network in {"", "none"}:
        network = "tcp"
    security = str(data.get("security") or data.get("tls") or "").strip().lower()
    ws_headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
    header_host = next(
        (value for key, value in ws_headers.items() if str(key).lower() == "host"),
        None,
    )
    host = data.get("host") or data.get("ws-host") or header_host
    path = data.get("path") or data.get("ws-path")
    return ParsedNode(
        original_name=name,
        type="vmess",
        server=str(server),
        port=_parse_port(port),
        uuid=str(raw_uuid),
        cipher=str(data.get("scy") or "auto"),
        network=network,
        security=security or None,
        tls=_as_bool(data.get("tls")) or security in {"tls", "reality"},
        sni=data.get("sni") or data.get("servername") or data.get("serverName") or host,
        host=host,
        path=path,
        fingerprint=data.get("fp") or data.get("fingerprint") or data.get("client-fingerprint"),
        public_key=data.get("pbk"),
        short_id=data.get("sid"),
        country=detect_country(name),
        metadata=data,
    )
