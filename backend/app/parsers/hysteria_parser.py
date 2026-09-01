"""Hysteria URI 解析。"""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote, urlparse

from app.parsers.base import ParseError, ParsedNode
from app.utils.country import detect_country


def parse_hysteria_uri(uri: str) -> ParsedNode:
    """把 hysteria:// 链接解析为 ParsedNode。"""

    if not uri.startswith("hysteria://"):
        raise ParseError("不是有效的 Hysteria 链接")
    parsed = urlparse(uri)
    if not parsed.hostname or parsed.port is None:
        raise ParseError("Hysteria 链接缺少服务器或端口")
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    name = unquote(parsed.fragment) if parsed.fragment else parsed.hostname
    return ParsedNode(
        original_name=name,
        type="hysteria",
        server=parsed.hostname,
        port=parsed.port,
        password=params.get("auth") or params.get("auth_str"),
        network="udp",
        tls=True,
        sni=params.get("sni"),
        country=detect_country(name),
        metadata=params,
    )
