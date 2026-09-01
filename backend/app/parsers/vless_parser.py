"""VLESS URI 解析。"""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote, urlparse

from app.parsers.base import ParseError, ParsedNode
from app.utils.country import detect_country


def parse_vless_uri(uri: str) -> ParsedNode:
    """把 vless:// 链接解析为 ParsedNode。"""

    if not uri.startswith("vless://"):
        raise ParseError("不是有效的 VLESS 链接")
    parsed = urlparse(uri)
    if not parsed.hostname or parsed.port is None:
        raise ParseError("VLESS 链接缺少服务器或端口")
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    name = unquote(parsed.fragment) if parsed.fragment else parsed.hostname
    uuid = parsed.username or ""
    if not uuid:
        raise ParseError("VLESS 链接缺少 UUID")
    return ParsedNode(
        original_name=name,
        type="vless",
        server=parsed.hostname,
        port=parsed.port,
        uuid=uuid,
        network=params.get("type"),
        security=params.get("security"),
        tls=params.get("tls", "").lower() == "true",
        sni=params.get("sni"),
        fingerprint=params.get("fp") or params.get("client-fingerprint"),
        public_key=params.get("pbk") or params.get("public-key"),
        short_id=params.get("sid") or params.get("short-id"),
        path=params.get("path") or params.get("ws-path"),
        host=params.get("host"),
        country=detect_country(name),
        metadata=params,
    )
