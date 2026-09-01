"""Shadowsocks URI 解析（兼容 SIP002 与旧式明文）。"""

from __future__ import annotations

import base64
from urllib.parse import unquote

from app.parsers.base import ParseError, ParsedNode
from app.parsers.detector import decode_base64
from app.utils.country import detect_country


def _decode_userinfo(userinfo: str) -> tuple[str, str]:
    """解析 method:password，优先尝试 Base64 解码。"""

    if ":" not in userinfo:
        raise ParseError("SS 链接缺少加密方式与密码")
    method, password = userinfo.split(":", 1)
    return method, password


def parse_ss_uri(uri: str) -> ParsedNode:
    """把 ss:// 链接解析为 ParsedNode。"""

    if not uri.startswith("ss://"):
        raise ParseError("不是有效的 Shadowsocks 链接")
    body = uri.removeprefix("ss://")
    userinfo, sep, hostport = body.partition("@")
    if not sep or not hostport:
        raise ParseError("SS 链接缺少 @ 分隔符")
    host, port_sep, port_text = hostport.rpartition(":")
    if not port_sep:
        raise ParseError("SS 链接缺少有效端口")
    name = ""
    port_and_fragment = port_text.split("#", 1)
    port_text = port_and_fragment[0]
    if len(port_and_fragment) == 2:
        name = port_and_fragment[1]
    if not port_text.isdigit():
        raise ParseError("SS 链接缺少有效端口")
    decoded = decode_base64(userinfo)
    if decoded and ":" in decoded:
        method, password = _decode_userinfo(decoded)
    else:
        method, password = _decode_userinfo(userinfo)
    name = unquote(name) if name else host
    return ParsedNode(
        original_name=name,
        type="shadowsocks",
        server=host,
        port=int(port_text),
        password=password,
        cipher=method,
        country=detect_country(name),
    )
