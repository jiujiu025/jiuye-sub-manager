"""sing-box 订阅导出器。"""

from __future__ import annotations

import json

from app.exporters.base import (
    BaseExporter,
    canonical_node_type,
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
    metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
    if str(metadata.get("insecure", "")).lower() in {"1", "true", "yes", "on"}:
        tls["insecure"] = True
    return tls


def _transport(node: Node) -> dict | None:
    """把 WebSocket 传输参数映射为 sing-box transport。"""

    network = (node.network or "").lower()
    metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
    if network == "ws":
        transport: dict = {"type": "ws"}
        if node.path:
            transport["path"] = node.path
        if node.host:
            transport["headers"] = {"Host": node.host}
        return transport
    if network == "grpc":
        service_name = node.path or metadata.get("serviceName") or metadata.get("service_name")
        return {"type": "grpc", **({"service_name": service_name} if service_name else {})}
    if network in {"http", "h2"}:
        transport = {"type": "http"}
        if node.host:
            transport["host"] = [node.host]
        if node.path:
            transport["path"] = node.path
        return transport
    return None


def _speed(metadata: dict, *keys: str) -> int | None:
    """读取 Hysteria 速度参数，并转换为 sing-box 要求的整数。"""

    for key in keys:
        value = metadata.get(key)
        if value is None or value == "":
            continue
        try:
            speed = int(value)
        except (TypeError, ValueError):
            continue
        if speed > 0:
            return speed
    return None


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
        node_type = canonical_node_type(node.type)
        if node_type == "vless":
            outbound = {
                "type": "vless", **common, "uuid": node.uuid, "tls": _tls(node)
            }
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            if metadata.get("flow"):
                outbound["flow"] = metadata["flow"]
        elif node_type == "vmess":
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            outbound = {
                "type": "vmess",
                **common,
                "uuid": node.uuid,
                "security": node.cipher or "auto",
                "alter_id": metadata.get("aid", metadata.get("alterId", 0)),
                "tls": _tls(node),
            }
        elif node_type == "trojan":
            outbound = {
                "type": "trojan", **common, "password": node.password, "tls": _tls(node)
            }
        elif node_type == "shadowsocks":
            outbound = {
                "type": "shadowsocks",
                **common,
                "method": node.cipher,
                "password": node.password,
            }
        elif node_type == "anytls":
            outbound = {
                "type": "anytls",
                **common,
                "password": node.password,
                "tls": _tls(node),
            }
        elif node_type == "socks":
            outbound = {
                "type": "socks",
                **common,
                "version": "5",
            }
            if node.username:
                outbound["username"] = node.username
            if node.password:
                outbound["password"] = node.password
        elif node_type == "http":
            outbound = {"type": "http", **common}
            if node.username:
                outbound["username"] = node.username
            if node.password:
                outbound["password"] = node.password
            if node.tls:
                outbound["tls"] = _tls(node)
        elif node_type == "hysteria":
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            outbound = {
                "type": "hysteria",
                **common,
                "tls": _tls(node),
            }
            if node.password:
                outbound["auth_str"] = node.password
            upload_speed = _speed(metadata, "up", "upmbps", "up_mbps")
            download_speed = _speed(metadata, "down", "downmbps", "down_mbps")
            if upload_speed is not None:
                outbound["up_mbps"] = upload_speed
            if download_speed is not None:
                outbound["down_mbps"] = download_speed
            if metadata.get("obfs"):
                outbound["obfs"] = metadata["obfs"]
        elif node_type == "hysteria2":
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            outbound = {
                "type": "hysteria2",
                **common,
                "password": node.password,
                "tls": _tls(node),
            }
            upload_speed = _speed(metadata, "up", "upmbps", "up_mbps")
            download_speed = _speed(metadata, "down", "downmbps", "down_mbps")
            if upload_speed is not None:
                outbound["up_mbps"] = upload_speed
            if download_speed is not None:
                outbound["down_mbps"] = download_speed
            if metadata.get("obfs"):
                outbound["obfs"] = {
                    "type": metadata["obfs"],
                    "password": metadata.get("obfs-password"),
                }
        elif node_type == "tuic":
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            outbound = {
                "type": "tuic",
                **common,
                "uuid": node.uuid,
                "password": node.password,
                "tls": _tls(node),
                "congestion_control": metadata.get("congestion_control", "bbr"),
            }
            if metadata.get("udp_relay_mode"):
                outbound["udp_relay_mode"] = metadata["udp_relay_mode"]
        else:
            raise ValueError(f"不支持导出的节点类型: {node.type}")
        transport = _transport(node)
        if transport:
            outbound["transport"] = transport
        return outbound
