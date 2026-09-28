"""标准节点 URI 导出器。"""

from __future__ import annotations

import base64
import json
from urllib.parse import quote, urlencode

from app.exporters.base import (
    BaseExporter,
    exportable_items_for_format,
    unique_display_names,
)
from app.models.node import Node


def _authority(server: str, port: int) -> str:
    """为 IPv6 服务器补充 URI 所需的方括号。"""

    if ":" in server and not server.startswith("["):
        server = f"[{server}]"
    return f"{server}:{port}"


def _fragment(name: str) -> str:
    return quote(name, safe="")


class UriExporter(BaseExporter):
    """输出 vless、vmess、ss、trojan URI，每行一个节点。"""

    def export(self, items: list[tuple[Node, str]], subscription_name: str | None = None) -> str:
        lines: list[str] = []
        for node, name in unique_display_names(
            exportable_items_for_format(items, "uri")
        ):
            try:
                lines.append(self._to_uri(node, name))
            except (TypeError, ValueError):
                continue
        return "\n".join(lines) + ("\n" if lines else "")

    @staticmethod
    def _to_uri(node: Node, name: str) -> str:
        authority = _authority(node.server, node.port)
        if node.type == "vless":
            params: dict[str, str] = {}
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            # 保留 VLESS 标准 URI 中容易影响 Reality/Vision 连接的参数。
            for key in ("encryption", "flow", "headerType", "spx", "packetEncoding"):
                value = metadata.get(key)
                if value is not None and str(value) != "":
                    params[key] = str(value)
            if "encryption" not in params:
                params["encryption"] = "none"
            if node.network:
                params["type"] = node.network
            security = str(node.security or "").lower()
            if security in {"tls", "reality"}:
                params["security"] = security
            elif node.tls:
                params["security"] = "tls"
            if node.sni:
                params["sni"] = node.sni
            if node.fingerprint:
                params["fp"] = node.fingerprint
            if node.public_key:
                params["pbk"] = node.public_key
            if node.short_id:
                params["sid"] = node.short_id
            if node.path:
                params["path"] = node.path
            if node.host:
                params["host"] = node.host
            query = urlencode(params)
            query_suffix = f"?{query}" if query else ""
            return f"vless://{quote(node.uuid or '', safe='')}@{authority}{query_suffix}#{_fragment(name)}"
        if node.type == "shadowsocks":
            auth = base64.urlsafe_b64encode(
                f"{node.cipher}:{node.password}".encode("utf-8")
            ).decode("ascii").rstrip("=")
            return f"ss://{auth}@{authority}#{_fragment(name)}"
        if node.type == "vmess":
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            payload = {
                "v": "2",
                "ps": name,
                "add": node.server,
                "port": node.port,
                "id": node.uuid,
                "aid": metadata.get("aid", metadata.get("alterId", 0)),
                "scy": node.cipher or "auto",
                "net": node.network or "tcp",
                "tls": "tls" if node.tls else "",
                "sni": node.sni or "",
                "host": node.host or "",
                "path": node.path or "",
            }
            encoded = base64.b64encode(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            ).decode("ascii")
            return f"vmess://{encoded}"
        if node.type == "trojan":
            params: dict[str, str] = {"security": "tls" if node.tls else "none"}
            if node.network:
                params["type"] = node.network
            if node.sni:
                params["sni"] = node.sni
            if node.fingerprint:
                params["fp"] = node.fingerprint
            if node.path:
                params["path"] = node.path
            if node.host:
                params["host"] = node.host
            return (
                f"trojan://{quote(node.password or '', safe='')}@{authority}"
                f"?{urlencode(params)}#{_fragment(name)}"
            )
        if node.type == "anytls":
            metadata = node.metadata_json if isinstance(node.metadata_json, dict) else {}
            params: dict[str, str] = {"security": "tls"}
            if node.sni:
                params["sni"] = node.sni
            if node.fingerprint:
                params["fp"] = node.fingerprint
            if metadata.get("insecure") is not None:
                params["insecure"] = str(metadata["insecure"])
            return (
                f"anytls://{quote(node.password or '', safe='')}@{authority}"
                f"?{urlencode(params)}#{_fragment(name)}"
            )
        raise ValueError(f"不支持导出的节点类型: {node.type}")
