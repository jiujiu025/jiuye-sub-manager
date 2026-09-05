"""Mihomo 订阅导出器。"""

from __future__ import annotations

from app.exporters.clash import ClashExporter


class MihomoExporter(ClashExporter):
    """Mihomo 使用与保守 Clash 配置相同的通用 YAML 输出。"""
