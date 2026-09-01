"""TUIC URI 解析。"""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote

from app.parsers.base import ParseError, ParsedNode
from app.utils.country import detect_country


def parse_tuic_uri(uri: str) -> ParsedNode:
    """把 tuic:// 链接解析为 ParsedNode。"""

    if not uri.startswith("tuic://"):
        raise ParseError("不是有效的 TUIC 链接")
    body = uri.removeprefix("tuic://")
    userinfo, sep, hostport = body.partition("@")
    if not sep or not hostport:
        raise ParseError("TUIC 链接缺少服务器")
    uuid, _, password = userinfo.partition(":")
    if not uuid:
        raise ParseError("TUIC 链接缺少 UUID")
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
        raise ParseError("TUIC 链接缺少有效端口")
    name = unquote(fragment) if fragment else host
    return ParsedNode(
        original_name=name,
        type="tuic",
        server=host,
        port=int(port_text),
        uuid=uuid,
        password=password or None,
        tls=True,
        sni=params.get("sni"),
        country=detect_country(name),
        metadata=params,
    )
