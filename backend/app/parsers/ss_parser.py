"""Shadowsocks URI 解析（兼容 SIP002 与旧式明文）。"""

from __future__ import annotations

import base64
import binascii
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


def _decode_sip002(value: str) -> str | None:
    """解码 SIP002 使用的 URL-safe Base64（允许省略填充）。"""

    compact = "".join(value.split())
    try:
        padding = "=" * (-len(compact) % 4)
        return base64.urlsafe_b64decode(compact + padding).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def parse_ss_uri(uri: str) -> ParsedNode:
    """把 ss:// 链接解析为 ParsedNode。"""

    if not uri.startswith("ss://"):
        raise ParseError("不是有效的 Shadowsocks 链接")
    body = uri.removeprefix("ss://")
    body, _, fragment = body.partition("#")
    userinfo, sep, hostport = body.partition("@")
    if sep and hostport:
        decoded = _decode_sip002(userinfo) or decode_base64(userinfo)
        auth = decoded if decoded and ":" in decoded else userinfo
    else:
        # SIP002 允许把 method:password@host:port 整体编码进 authority。
        decoded = _decode_sip002(body)
        if not decoded or "@" not in decoded:
            raise ParseError("SS 链接缺少有效的 SIP002 内容")
        auth, _, hostport = decoded.rpartition("@")

    host, port_sep, port_text = hostport.rpartition(":")
    if not port_sep:
        raise ParseError("SS 链接缺少有效端口")
    if not port_text.isdigit():
        raise ParseError("SS 链接缺少有效端口")
    method, password = _decode_userinfo(auth)
    name = unquote(fragment) if fragment else host
    return ParsedNode(
        original_name=name,
        type="shadowsocks",
        server=host,
        port=int(port_text),
        password=password,
        cipher=method,
        country=detect_country(name),
    )
