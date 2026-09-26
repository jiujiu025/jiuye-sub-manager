"""AnyTLS URI 解析。"""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote, urlparse

from app.parsers.base import ParseError, ParsedNode
from app.utils.country import detect_country


def parse_anytls_uri(uri: str) -> ParsedNode:
    """把 anytls:// 链接解析为统一节点结构。"""

    if not uri.startswith("anytls://"):
        raise ParseError("不是有效的 AnyTLS 链接")
    try:
        parsed = urlparse(uri)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ParseError("AnyTLS 链接的服务器或端口无效") from exc
    if not hostname or port is None:
        raise ParseError("AnyTLS 链接缺少服务器或端口")
    password = unquote(parsed.username or "")
    if not password:
        raise ParseError("AnyTLS 链接缺少密码")
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    security = (params.get("security") or "tls").strip().lower()
    name = unquote(parsed.fragment) if parsed.fragment else hostname
    return ParsedNode(
        original_name=name,
        type="anytls",
        server=hostname,
        port=port,
        password=password,
        network=params.get("type") or "tcp",
        security=security,
        tls=security not in {"none", "false", "0"},
        sni=params.get("sni") or params.get("servername"),
        fingerprint=params.get("fp") or params.get("fingerprint"),
        country=detect_country(name),
        metadata=params,
    )
