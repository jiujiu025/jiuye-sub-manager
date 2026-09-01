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


class BaseParser(ABC):
    """所有订阅解析器必须实现 parse 方法。"""

    @abstractmethod
    def parse(self, content: str) -> list[ParsedNode]:
        """把指定格式内容解析为 ParsedNode 列表。"""
