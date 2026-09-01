"""Clash/Mihomo 导出器单元测试。"""

from __future__ import annotations

from app.exporters.clash import ClashExporter
from app.models.node import Node
from app.utils.fingerprint import build_node_fingerprint


def _make_node(
    *,
    name: str,
    node_type: str,
    server: str,
    port: int,
    uuid: str | None = None,
    password: str | None = None,
    cipher: str | None = None,
    **kwargs,
) -> Node:
    return Node(
        source_id=None,
        source_name="自有节点",
        original_name=name,
        name=name,
        type=node_type,
        server=server,
        port=port,
        uuid=uuid,
        password=password,
        cipher=cipher,
        node_fingerprint=build_node_fingerprint(
            node_type=node_type,
            server=server,
            port=port,
            uuid=uuid,
            password=password,
            cipher=cipher,
        ),
        **kwargs,
    )


def test_export_vless_reality() -> None:
    """VLESS Reality 节点应输出完整 Clash 字段。"""

    node = _make_node(
        name="HK-01",
        node_type="vless",
        server="hk.example.com",
        port=443,
        uuid="uuid-secret",
        network="tcp",
        security="reality",
        tls=True,
        sni="hk.example.com",
        fingerprint="chrome",
        public_key="pbk-secret",
        short_id="sid-secret",
        metadata_json={"flow": "xtls-rprx-vision"},
    )
    yaml_text = ClashExporter().export([(node, "HK-01")])
    assert "HK-01" in yaml_text
    assert "type: vless" in yaml_text
    assert "uuid-secret" in yaml_text
    assert "reality-opts:" in yaml_text
    assert "pbk-secret" in yaml_text
    assert "sid-secret" in yaml_text
    assert "xtls-rprx-vision" in yaml_text


def test_export_shadowsocks() -> None:
    """Shadowsocks 节点应输出 ss 类型与加密字段。"""

    node = _make_node(
        name="JP-SS",
        node_type="shadowsocks",
        server="jp.example.com",
        port=8388,
        password="password-secret",
        cipher="aes-256-gcm",
    )
    yaml_text = ClashExporter().export([(node, "JP-SS")])
    assert "type: ss" in yaml_text
    assert "password-secret" in yaml_text
    assert "aes-256-gcm" in yaml_text


def test_export_never_exposes_upstream_url() -> None:
    """输出不应包含 proxy-providers、上游 URL 或原始订阅 URL。"""

    node = _make_node(
        name="HK-01",
        node_type="vless",
        server="hk.example.com",
        port=443,
        uuid="uuid-secret",
        metadata_json={"url": "https://secret-provider.example.com/sub/abc"},
    )
    yaml_text = ClashExporter().export([(node, "HK-01")])
    assert "proxy-providers" not in yaml_text
    assert "secret-provider" not in yaml_text
    assert "/sub/abc" not in yaml_text
