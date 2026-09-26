"""sing-box 订阅导出器。"""

from __future__ import annotations

import json

from app.exporters.base import (
    BaseExporter,
    exportable_items_for_format,
    unique_display_names,
)
from app.models.node import Node


def _tls(node: Node) -> dict:
    """把 TLS、指纹和 Reality 参数映射为 sing-box TLS 配置。"""

    enabled = bool(node.tls) or str(node.security or "").lower() in {"tls", "reality"}
    tls: dict = {"enabled": enabled}
    if node.sni:
        tls["server_name"] = node.sni
    if node.fingerprint:
        tls["utls"] = {"enabled": True, "fingerprint": node.fingerprint}
    is_reality = str(node.security or "").lower() == "reality" or bool(
        node.public_key or node.short_id
    )
    if is_reality:
        reality: dict = {"enabled": True}
        if node.public_key:
            reality["public_key"] = node.public_key
        if node.short_id:
            reality["short_id"] = node.short_id
        tls["enabled"] = True
        tls["reality"] = reality
    return tls


def _transport(node: Node) -> dict | None:
    """把 WebSocket 传输参数映射为 sing-box transport。"""

    if node.network != "ws":
        return None
    transport: dict = {"type": "ws"}
    if node.path:
        transport["path"] = node.path
    if node.host:
        transport["headers"] = {"Host": node.host}
    return transport


class SingboxExporter(BaseExporter):
    """生成标准 sing-box JSON 配置。"""

    def export(
        self,
        items: list[tuple[Node, str]],
        subscription_name: str | None = None,
    ) -> str:
        safe_items = unique_display_names(
            exportable_items_for_format(items, "singbox")
        )
        outbounds = [self._to_outbound(node, name) for node, name in safe_items]
        tags = [name for _, name in safe_items]
        selector = {"type": "selector", "tag": "Proxy", "outbounds": tags}
        config = {
            "outbounds": [selector, *outbounds, {"type": "direct", "tag": "direct"}],
            "route": {"final": "Proxy"},
        }
        return json.dumps(config, ensure_ascii=False, indent=2) + "\n"

    @staticmethod
    def _to_outbound(node: Node, name: str) -> dict:
        common = {"tag": name, "server": node.server, "server_port": node.port}
        if node.type == "vless":
            outbound = {
                "type": "vless", **common, "uuid": node.uuid, "tls": _tls(node)
            }
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            if metadata.get("flow"):
                outbound["flow"] = metadata["flow"]
        elif node.type == "vmess":
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            outbound = {
                "type": "vmess",
                **common,
                "uuid": node.uuid,
                "security": node.cipher or "auto",
                "alter_id": metadata.get("aid", metadata.get("alterId", 0)),
                "tls": _tls(node),
            }
        elif node.type == "trojan":
            outbound = {
                "type": "trojan", **common, "password": node.password, "tls": _tls(node)
            }
        elif node.type == "shadowsocks":
            outbound = {
                "type": "shadowsocks",
                **common,
                "method": node.cipher,
                "password": node.password,
            }
        elif node.type == "anytls":
            outbound = {
                "type": "anytls",
                **common,
                "password": node.password,
                "tls": _tls(node),
            }
        else:
            raise ValueError(f"不支持导出的节点类型: {node.type}")
        transport = _transport(node)
        if transport:
            outbound["transport"] = transport
        return outbound
