"""Clash/Mihomo 订阅导出器。"""

from __future__ import annotations

import yaml

from app.exporters.base import BaseExporter
from app.models.node import Node


class ClashExporter(BaseExporter):
    """生成只包含解析后节点的 Clash/Mihomo proxies 配置。"""

    def export(self, items: list[tuple[Node, str]]) -> str:
        proxies = [self._to_proxy(node, name) for node, name in items]
        data = {"proxies": proxies}
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    @staticmethod
    def _to_proxy(node: Node, name: str) -> dict:
        if node.type == "vless":
            return ClashExporter._to_vless(node, name)
        if node.type == "shadowsocks":
            return ClashExporter._to_ss(node, name)
        return {
            "name": name,
            "type": node.type,
            "server": node.server,
            "port": node.port,
        }

    @staticmethod
    def _to_vless(node: Node, name: str) -> dict:
        proxy: dict = {
            "name": name,
            "type": "vless",
            "server": node.server,
            "port": node.port,
            "uuid": node.uuid,
            "network": node.network or "tcp",
            "tls": bool(node.tls),
            "udp": True,
        }
        if node.sni:
            proxy["servername"] = node.sni
        if node.fingerprint:
            proxy["client-fingerprint"] = node.fingerprint
        if node.public_key or node.short_id:
            reality_opts: dict = {}
            if node.public_key:
                reality_opts["public-key"] = node.public_key
            if node.short_id:
                reality_opts["short-id"] = node.short_id
            proxy["reality-opts"] = reality_opts
        if node.network == "ws":
            ws_opts: dict = {}
            if node.path:
                ws_opts["path"] = node.path
            if node.host:
                ws_opts["headers"] = {"Host": node.host}
            if ws_opts:
                proxy["ws-opts"] = ws_opts
        if isinstance(node.metadata_json, dict) and node.metadata_json.get("flow"):
            proxy["flow"] = node.metadata_json["flow"]
        return proxy

    @staticmethod
    def _to_ss(node: Node, name: str) -> dict:
        return {
            "name": name,
            "type": "ss",
            "server": node.server,
            "port": node.port,
            "cipher": node.cipher,
            "password": node.password,
            "udp": True,
        }
