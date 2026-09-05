"""解析器基类与统一节点数据结构。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ParseError(Exception):
    """订阅解析失败异常。"""


@dataclass
class ParsedNode:
    """解析后的统一节点，业务层只操作该结构。"""

    original_name: str
    type: str
    server: str
    port: int
    uuid: str | None = None
    password: str | None = None
    username: str | None = None
    cipher: str | None = None
    network: str | None = None
    security: str | None = None
    tls: bool | None = None
    sni: str | None = None
    fingerprint: str | None = None
    public_key: str | None = None
    short_id: str | None = None
    path: str | None = None
    host: str | None = None
    country: str | None = None
    metadata: dict = field(default_factory=dict)


def validate_parsed_node(node: ParsedNode) -> None:
    """校验解析结果的协议必填字段，避免无效节点进入节点池。"""

    if (
        not isinstance(node.server, str)
        or not node.server.strip()
        or isinstance(node.port, bool)
        or not isinstance(node.port, int)
        or not 0 < node.port < 65536
    ):
        raise ParseError("节点服务器或端口无效")

    if node.type in {"vless", "vmess", "tuic"} and (
        not isinstance(node.uuid, str) or not node.uuid.strip()
    ):
        raise ParseError(f"{node.type.upper()} 节点缺少 UUID")
    if node.type == "shadowsocks" and (
        not isinstance(node.cipher, str)
        or not node.cipher.strip()
        or not isinstance(node.password, str)
        or not node.password.strip()
    ):
        raise ParseError("Shadowsocks 节点缺少加密方式或密码")
    if node.type in {"trojan", "hysteria", "hysteria2"} and (
        not isinstance(node.password, str) or not node.password.strip()
    ):
        raise ParseError(f"{node.type.upper()} 节点缺少密码")


class BaseParser(ABC):
    """所有订阅解析器必须实现 parse 方法。"""

    @abstractmethod
    def parse(self, content: str) -> list[ParsedNode]:
        """把指定格式内容解析为 ParsedNode 列表。"""
