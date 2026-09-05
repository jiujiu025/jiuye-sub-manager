"""按行解析 vless/ss 等 URI 订阅。"""

from __future__ import annotations

from app.parsers.base import ParseError, ParsedNode
from app.parsers.http_parser import parse_http_uri
from app.parsers.hysteria2_parser import parse_hysteria2_uri
from app.parsers.hysteria_parser import parse_hysteria_uri
from app.parsers.socks_parser import parse_socks_uri
from app.parsers.ss_parser import parse_ss_uri
from app.parsers.trojan_parser import parse_trojan_uri
from app.parsers.tuic_parser import parse_tuic_uri
from app.parsers.vless_parser import parse_vless_uri
from app.parsers.vmess_parser import parse_vmess_uri


def parse_uri_line(line: str, forced: str | None = None) -> ParsedNode:
    """解析单行节点链接；解析失败抛出 ParseError。"""

    if "\\://" in line:
        line = line.replace("\\://", "://", 1)
    if forced == "vless":
        return parse_vless_uri(line)
    if forced == "vmess":
        return parse_vmess_uri(line)
    if forced == "ss":
        return parse_ss_uri(line)
    if forced == "trojan":
        return parse_trojan_uri(line)
    if forced == "socks":
        return parse_socks_uri(line)
    if forced == "http":
        return parse_http_uri(line)
    if forced == "hysteria":
        return parse_hysteria_uri(line)
    if forced == "hysteria2":
        return parse_hysteria2_uri(line)
    if forced == "tuic":
        return parse_tuic_uri(line)
    if line.startswith("vless://"):
        return parse_vless_uri(line)
    if line.startswith("vmess://"):
        return parse_vmess_uri(line)
    if line.startswith("ss://"):
        return parse_ss_uri(line)
    if line.startswith("trojan://"):
        return parse_trojan_uri(line)
    if line.startswith("socks://") or line.startswith("socks5://"):
        return parse_socks_uri(line)
    if line.startswith("http://") or line.startswith("https://"):
        return parse_http_uri(line)
    if line.startswith("hysteria://"):
        return parse_hysteria_uri(line)
    if line.startswith("hysteria2://") or line.startswith("hy2://"):
        return parse_hysteria2_uri(line)
    if line.startswith("tuic://"):
        return parse_tuic_uri(line)
    raise ParseError("无法识别的节点链接")


def parse_uri_lines(content: str) -> list[ParsedNode]:
    """逐行解析 URI 订阅，忽略无法解析的行。"""

    nodes: list[ParsedNode] = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            nodes.append(parse_uri_line(line))
        except ParseError:
            continue
    return nodes
