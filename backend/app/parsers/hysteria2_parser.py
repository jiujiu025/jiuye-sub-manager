"""Hysteria2 URI 解析。"""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote

from app.parsers.base import ParseError, ParsedNode
from app.utils.country import detect_country


def parse_hysteria2_uri(uri: str) -> ParsedNode:
    """把 hysteria2:// 或 hy2:// 链接解析为 ParsedNode。"""

    if not (uri.startswith("hysteria2://") or uri.startswith("hy2://")):
        raise ParseError("不是有效的 Hysteria2 链接")
    body = uri.split("://", 1)[1]
    password, sep, hostport = body.partition("@")
    if not sep:
        password = ""
        hostport = body
    fragment = ""
    query_index = hostport.find("?")
    if query_index >= 0:
        query_text = hostport[query_index + 1 :]
        hostport = hostport[:query_index]
        fragment_index = query_text.find("#")
        if fragment_index >= 0:
            query_text, fragment = query_text[:fragment_index], query_text[fragment_index + 1 :]
        params = dict(parse_qsl(query_text, keep_blank_values=True))
    else:
        params = {}
        fragment_index = hostport.find("#")
        if fragment_index >= 0:
            hostport, fragment = hostport[:fragment_index], hostport[fragment_index + 1 :]
    host, port_sep, port_text = hostport.rpartition(":")
    if not port_sep or not port_text.isdigit():
        raise ParseError("Hysteria2 链接缺少有效端口")
    name = unquote(fragment) if fragment else host
    return ParsedNode(
        original_name=name,
        type="hysteria2",
        server=host,
        port=int(port_text),
        password=password,
        network="udp",
        tls=params.get("insecure", "0").lower() not in ("1", "true"),
        sni=params.get("sni"),
        country=detect_country(name),
        metadata=params,
    )
