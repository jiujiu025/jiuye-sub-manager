"""订阅输出模块。"""

from app.exporters.clash import ClashExporter
from app.exporters.mihomo import MihomoExporter
from app.exporters.singbox import SingboxExporter
from app.exporters.uri import UriExporter


def export_nodes(
    items: list[tuple[object, str]],
    output_format: str,
    subscription_name: str | None = None,
) -> tuple[str, int]:
    """按客户端格式导出节点，并返回内容与实际导出节点数。"""

    exporters = {
        "clash": ClashExporter(),
        "mihomo": MihomoExporter(),
        "singbox": SingboxExporter(),
        "uri": UriExporter(),
    }
    exporter = exporters[output_format]
    content = exporter.export(items, subscription_name=subscription_name)
    from app.exporters.base import exportable_items_for_format

    return content, len(exportable_items_for_format(items, output_format))

__all__ = [
    "ClashExporter",
    "MihomoExporter",
    "SingboxExporter",
    "UriExporter",
    "export_nodes",
    "resolve_output_format",
]


def resolve_output_format(client: str | None, user_agent: str | None) -> str:
    """解析显式 client 或根据 User-Agent 选择订阅格式。"""

    supported = {"clash", "mihomo", "singbox", "uri"}
    if client:
        output_format = client.strip().lower()
        if output_format not in supported:
            raise ValueError("不支持的订阅格式")
        return output_format
    agent = (user_agent or "").lower()
    if "sing-box" in agent or "singbox" in agent:
        return "singbox"
    if "mihomo" in agent or "clash.meta" in agent or "clashmeta" in agent:
        return "mihomo"
    if "shadowrocket" in agent or "stash" in agent:
        return "uri"
    return "clash"
