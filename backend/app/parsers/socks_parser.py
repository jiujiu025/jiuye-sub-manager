"""SOCKS URI 解析（兼容 socks:// 与 socks5://）。"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

from app.parsers.base import ParseError, ParsedNode
from app.utils.country import detect_country


def parse_socks_uri(uri: str) -> ParsedNode:
    """把 socks/socks5:// 链接解析为 ParsedNode。"""

    if not (uri.startswith("socks://") or uri.startswith("socks5://")):
        raise ParseError("不是有效的 SOCKS 链接")
    parsed = urlparse(uri)
    if not parsed.hostname or parsed.port is None:
        raise ParseError("SOCKS 链接缺少服务器或端口")
    name = unquote(parsed.fragment) if parsed.fragment else parsed.hostname
    return ParsedNode(
        original_name=name,
        type="socks",
        server=parsed.hostname,
        port=parsed.port,
        username=parsed.username,
        password=parsed.password,
        country=detect_country(name),
    )
