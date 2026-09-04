"""Clash/Mihomo 订阅导出器。"""

from __future__ import annotations

import yaml

from app.exporters.base import BaseExporter
from app.models.node import Node


class ClashExporter(BaseExporter):
    """生成只包含解析后节点的 Clash/Mihomo proxies 配置。"""

    def export(
        self,
        items: list[tuple[Node, str]],
        subscription_name: str | None = None,
    ) -> str:
        proxies = [self._to_proxy(node, name) for node, name in items]
        data: dict = {}
        if subscription_name:
            data["sub-name"] = subscription_name
        data["proxies"] = proxies
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    @staticmethod
    def _to_proxy(node: Node, name: str) -> dict:
        if node.type == "vless":
            return ClashExporter._to_vless(node, name)
        if node.type == "shadowsocks":
            return ClashExporter._to_ss(node, name)
        if node.type == "vmess":
            return ClashExporter._to_vmess(node, name)
        if node.type == "trojan":
            return ClashExporter._to_trojan(node, name)
        if node.type == "socks":
            return ClashExporter._to_socks(node, name)
        if node.type == "http":
            return ClashExporter._to_http(node, name)
        if node.type == "hysteria":
            return ClashExporter._to_hysteria(node, name)
        if node.type == "hysteria2":
            return ClashExporter._to_hysteria2(node, name)
        if node.type == "tuic":
            return ClashExporter._to_tuic(node, name)
        return {
            "name": name,
            "type": node.type,
            "server": node.server,
            "port": node.port,
        }

    @staticmethod
    def _to_vless(node: Node, name: str) -> dict:
        is_reality = (
            node.security == "reality"
            or bool(node.public_key)
            or bool(node.short_id)
        )
        proxy: dict = {
            "name": name,
            "type": "vless",
            "server": node.server,
            "port": node.port,
            "uuid": node.uuid,
            "network": node.network or "tcp",
            "tls": bool(node.tls)
            or str(node.security or "").lower() == "tls"
            or is_reality,
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

    @staticmethod
    def _ws_opts(node: Node) -> dict | None:
        if node.network != "ws":
            return None
        ws_opts: dict = {}
        if node.path:
            ws_opts["path"] = node.path
        if node.host:
            ws_opts["headers"] = {"Host": node.host}
        return ws_opts or None

    @staticmethod
    def _to_vmess(node: Node, name: str) -> dict:
        metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
        proxy: dict = {
            "name": name,
            "type": "vmess",
            "server": node.server,
            "port": node.port,
            "uuid": node.uuid,
            "alterId": metadata.get("aid", metadata.get("alterId", 0)),
            "cipher": node.cipher or "auto",
            "network": node.network or "tcp",
            "tls": bool(node.tls),
            "udp": True,
        }
        if node.sni:
            proxy["servername"] = node.sni
        if node.fingerprint:
            proxy["client-fingerprint"] = node.fingerprint
        ws_opts = ClashExporter._ws_opts(node)
        if ws_opts:
            proxy["ws-opts"] = ws_opts
        return proxy

    @staticmethod
    def _to_trojan(node: Node, name: str) -> dict:
        proxy: dict = {
            "name": name,
            "type": "trojan",
            "server": node.server,
            "port": node.port,
            "password": node.password,
            "network": node.network or "tcp",
            "tls": bool(node.tls),
            "udp": True,
        }
        if node.sni:
            proxy["servername"] = node.sni
        if node.fingerprint:
            proxy["client-fingerprint"] = node.fingerprint
        ws_opts = ClashExporter._ws_opts(node)
        if ws_opts:
            proxy["ws-opts"] = ws_opts
        return proxy

    @staticmethod
    def _to_socks(node: Node, name: str) -> dict:
        proxy: dict = {
            "name": name,
            "type": "socks5",
            "server": node.server,
            "port": node.port,
            "udp": True,
        }
        if node.username:
            proxy["username"] = node.username
        if node.password:
            proxy["password"] = node.password
        if node.tls:
            proxy["tls"] = True
        if node.sni:
            proxy["sni"] = node.sni
        return proxy

    @staticmethod
    def _to_http(node: Node, name: str) -> dict:
        proxy: dict = {
            "name": name,
            "type": "http",
            "server": node.server,
            "port": node.port,
        }
        if node.username:
            proxy["username"] = node.username
        if node.password:
            proxy["password"] = node.password
        if node.tls:
            proxy["tls"] = True
            if node.sni:
                proxy["sni"] = node.sni
        return proxy

    @staticmethod
    def _to_hysteria(node: Node, name: str) -> dict:
        metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
        proxy: dict = {
            "name": name,
            "type": "hysteria",
            "server": node.server,
            "port": node.port,
            "protocol": metadata.get("protocol") or "udp",
        }
        if node.password:
            proxy["auth_str"] = node.password
        if metadata.get("up"):
            proxy["up"] = metadata["up"]
        if metadata.get("down"):
            proxy["down"] = metadata["down"]
        if node.sni:
            proxy["sni"] = node.sni
        return proxy

    @staticmethod
    def _to_hysteria2(node: Node, name: str) -> dict:
        metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
        proxy: dict = {
            "name": name,
            "type": "hysteria2",
            "server": node.server,
            "port": node.port,
            "password": node.password,
            "udp": True,
        }
        if node.sni:
            proxy["sni"] = node.sni
        if metadata.get("up"):
            proxy["up"] = metadata["up"]
        if metadata.get("down"):
            proxy["down"] = metadata["down"]
        return proxy

    @staticmethod
    def _to_tuic(node: Node, name: str) -> dict:
        proxy: dict = {
            "name": name,
            "type": "tuic",
            "server": node.server,
            "port": node.port,
            "uuid": node.uuid,
            "udp": True,
        }
        if node.password:
            proxy["password"] = node.password
        if node.sni:
            proxy["sni"] = node.sni
        return proxy
