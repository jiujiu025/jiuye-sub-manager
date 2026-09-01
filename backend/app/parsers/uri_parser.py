"""按行解析 vless/ss 等 URI 订阅。"""

from __future__ import annotations

from app.parsers.base import ParseError, ParsedNode
from app.parsers.ss_parser import parse_ss_uri
from app.parsers.vless_parser import parse_vless_uri


def parse_uri_lines(content: str) -> list[ParsedNode]:
    """逐行解析 URI 订阅，忽略无法解析的行。"""

    nodes: list[ParsedNode] = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            if line.startswith("vless://"):
                nodes.append(parse_vless_uri(line))
            elif line.startswith("ss://"):
                nodes.append(parse_ss_uri(line))
        except ParseError:
            continue
    return nodes
