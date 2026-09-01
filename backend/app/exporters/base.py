"""导出器基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.node import Node


class BaseExporter(ABC):
    """所有导出器接收 (Node, 展示名) 有序列表并生成订阅文本。"""

    @abstractmethod
    def export(self, items: list[tuple[Node, str]]) -> str:
        """把节点列表导出为订阅配置文本。"""
