"""标准 Base64 节点订阅导出器。"""

from __future__ import annotations

import base64

from app.exporters.base import BaseExporter
from app.exporters.uri import UriExporter
from app.models.node import Node


class Base64Exporter(BaseExporter):
    """输出 V2RayN、V2RayNG、Hiddify、NekoBox 常用的 Base64 URI 订阅。"""

    def export(
        self,
        items: list[tuple[Node, str]],
        subscription_name: str | None = None,
    ) -> str:
        uri_content = UriExporter().export(items, subscription_name=subscription_name)
        if not uri_content:
            return ""
        return base64.b64encode(uri_content.encode("utf-8")).decode("ascii") + "\n"
