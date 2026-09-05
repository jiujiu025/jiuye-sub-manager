"""HTTP/HTTPS 代理 URI 解析。"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

from app.parsers.base import ParseError, ParsedNode
from app.utils.country import detect_country


def parse_http_uri(uri: str) -> ParsedNode:
    """把 http/https:// 代理链接解析为 ParsedNode。"""

    if not (uri.startswith("http://") or uri.startswith("https://")):
        raise ParseError("不是有效的 HTTP 代理链接")
    parsed = urlparse(uri)
    if not parsed.hostname or parsed.port is None:
        raise ParseError("HTTP 代理链接缺少服务器或端口")
    name = unquote(parsed.fragment) if parsed.fragment else parsed.hostname
    return ParsedNode(
        original_name=name,
        type="http",
        server=parsed.hostname,
        port=parsed.port,
        username=parsed.username,
        password=parsed.password,
        tls=parsed.scheme == "https",
        country=detect_country(name),
    )
