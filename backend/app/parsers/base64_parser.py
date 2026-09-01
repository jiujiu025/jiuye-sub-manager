"""Base64 订阅解析。"""

from __future__ import annotations

from app.parsers.base import BaseParser, ParsedNode
from app.parsers.detector import decode_base64
from app.parsers.uri_parser import parse_uri_lines


class Base64Parser(BaseParser):
    """把 Base64 内容解码后按 URI 行解析。"""

    def parse(self, content: str) -> list[ParsedNode]:
        decoded = decode_base64(content)
        if decoded is None:
            return []
        return parse_uri_lines(decoded)
