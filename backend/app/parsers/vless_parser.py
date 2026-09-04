"""VLESS URI 解析。"""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote, urlparse

from app.parsers.base import ParseError, ParsedNode
from app.utils.country import detect_country


def parse_vless_uri(uri: str) -> ParsedNode:
    """把 vless:// 链接解析为 ParsedNode。"""

    if not uri.startswith("vless://"):
        raise ParseError("不是有效的 VLESS 链接")
    try:
        parsed = urlparse(uri)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ParseError("VLESS 链接的服务器或端口无效") from exc
    if not hostname or port is None:
        raise ParseError("VLESS 链接缺少服务器或端口")
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    name = unquote(parsed.fragment) if parsed.fragment else parsed.hostname
    uuid = parsed.username or ""
    if not uuid:
        raise ParseError("VLESS 链接缺少 UUID")
    security = (params.get("security") or "").strip().lower()
    is_reality = (
        security == "reality"
        or bool(params.get("pbk") or params.get("public-key"))
        or bool(params.get("sid") or params.get("short-id"))
    )
    return ParsedNode(
        original_name=name,
        type="vless",
        server=hostname,
        port=port,
        uuid=uuid,
        network=params.get("type"),
        security=security or None,
        tls=(params.get("tls", "").lower() == "true")
        or security in {"tls", "reality"}
        or is_reality,
        sni=params.get("sni"),
        fingerprint=params.get("fp") or params.get("client-fingerprint"),
        public_key=params.get("pbk") or params.get("public-key"),
        short_id=params.get("sid") or params.get("short-id"),
        path=params.get("path") or params.get("ws-path"),
        host=params.get("host"),
        country=detect_country(name),
        metadata=params,
    )
