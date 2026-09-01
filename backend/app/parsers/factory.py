"""解析器工厂与统一入口。"""

from __future__ import annotations

from app.parsers.base import ParseError, ParsedNode
from app.parsers.base64_parser import Base64Parser
from app.parsers.clash_parser import ClashParser
from app.parsers.detector import detect_format, detect_uri_type
from app.parsers.http_parser import parse_http_uri
from app.parsers.hysteria2_parser import parse_hysteria2_uri
from app.parsers.hysteria_parser import parse_hysteria_uri
from app.parsers.singbox_parser import SingboxParser
from app.parsers.socks_parser import parse_socks_uri
from app.parsers.ss_parser import parse_ss_uri
from app.parsers.trojan_parser import parse_trojan_uri
from app.parsers.tuic_parser import parse_tuic_uri
from app.parsers.uri_parser import parse_uri_lines
from app.parsers.vless_parser import parse_vless_uri
from app.parsers.vmess_parser import parse_vmess_uri


class ParserFactory:
    """按格式选择解析器，业务层通过该工厂访问。"""

    def __init__(self) -> None:
        self._parsers = {
            "base64": Base64Parser(),
            "clash": ClashParser(),
            "singbox": SingboxParser(),
        }

    def parse(self, content: str, fmt: str = "auto") -> list[ParsedNode]:
        """解析订阅内容；fmt 为 auto 时自动检测。"""

        actual_format = detect_format(content) if fmt == "auto" else fmt
        if actual_format == "unknown":
            raise ParseError("无法识别订阅格式")
        if actual_format == "uri":
            return parse_uri_lines(content)
        if actual_format == "vless":
            return [parse_vless_uri(line) for line in content.strip().splitlines() if line.strip()]
        if actual_format == "ss":
            return [parse_ss_uri(line) for line in content.strip().splitlines() if line.strip()]
        if actual_format == "vmess":
            return [parse_vmess_uri(line) for line in content.strip().splitlines() if line.strip()]
        if actual_format == "trojan":
            return [parse_trojan_uri(line) for line in content.strip().splitlines() if line.strip()]
        if actual_format == "socks":
            return [parse_socks_uri(line) for line in content.strip().splitlines() if line.strip()]
        if actual_format == "http":
            return [parse_http_uri(line) for line in content.strip().splitlines() if line.strip()]
        parser = self._parsers.get(actual_format)
        if parser is None:
            raise ParseError(f"不支持的订阅格式: {actual_format}")
        return parser.parse(content)


def parse_content(content: str, fmt: str = "auto") -> list[ParsedNode]:
    """便捷函数：解析订阅内容为统一节点列表。"""

    return ParserFactory().parse(content, fmt)
