"""Trojan URI 解析。"""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote

from app.parsers.base import ParseError, ParsedNode
from app.utils.country import detect_country


def parse_trojan_uri(uri: str) -> ParsedNode:
    """把 trojan:// 链接解析为 ParsedNode。"""

    if not uri.startswith("trojan://"):
        raise ParseError("不是有效的 Trojan 链接")
    body = uri.removeprefix("trojan://")
    password, sep, hostport = body.partition("@")
    if not sep or not password or not hostport:
        raise ParseError("Trojan 链接缺少密码或服务器")
    query_start = hostport.find("?")
    fragment = ""
    if query_start >= 0:
        query_text = hostport[query_start + 1 :]
        hostport = hostport[:query_start]
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
        raise ParseError("Trojan 链接缺少有效端口")
    name = unquote(fragment) if fragment else host
    return ParsedNode(
        original_name=name,
        type="trojan",
        server=host,
        port=int(port_text),
        password=password,
        network=params.get("type"),
        tls=params.get("security", "tls").lower() in ("tls", "reality", "true"),
        sni=params.get("sni"),
        host=params.get("host"),
        path=params.get("path"),
        fingerprint=params.get("fp") or params.get("client-fingerprint"),
        public_key=params.get("pbk") or params.get("public-key"),
        short_id=params.get("sid") or params.get("short-id"),
        country=detect_country(name),
        metadata=params,
    )
