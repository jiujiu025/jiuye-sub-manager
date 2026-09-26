"""Clash/Mihomo 导出器单元测试。"""

from __future__ import annotations

import json

import yaml

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
    assert "tls: true" in yaml_text


def test_singbox_vless_reality_preserves_flow() -> None:
    """Sing-box VLESS Reality 必须保留 xtls flow。"""

    node = _make_node(
        name="Reality-flow",
        node_type="vless",
        server="reality-flow.example.com",
        port=443,
        uuid="00000000-0000-0000-0000-000000000100",
        security="reality",
        tls=True,
        sni="www.example.com",
        public_key="public-key",
        short_id="short-id",
        metadata_json={"flow": "xtls-rprx-vision"},
    )

    from app.exporters.singbox import SingboxExporter

    data = json.loads(SingboxExporter().export([(node, node.name)]))
    outbound = next(item for item in data["outbounds"] if item["tag"] == node.name)
    assert outbound["flow"] == "xtls-rprx-vision"


def test_export_plain_vless_tls_unchanged() -> None:
    """普通 VLESS（无 Reality 字段）的 tls 状态不应被强制改为 true。"""

    node = _make_node(
        name="HK-01",
        node_type="vless",
        server="hk.example.com",
        port=443,
        uuid="uuid-secret",
        tls=False,
    )
    yaml_text = ClashExporter().export([(node, "HK-01")])
    data = yaml.safe_load(yaml_text)
    assert data["proxies"][0]["tls"] is False


def test_export_vless_security_tls_enables_tls() -> None:
    """VLESS security=tls 即使旧数据 tls 为空也应输出 tls=true。"""

    node = _make_node(
        name="TLS-01",
        node_type="vless",
        server="tls.example.com",
        port=443,
        uuid="uuid-tls",
        security="tls",
        tls=False,
    )
    data = yaml.safe_load(ClashExporter().export([(node, "TLS-01")]))
    assert data["proxies"][0]["tls"] is True


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


def test_export_anytls_formats() -> None:
    """AnyTLS 应能导出 Clash、sing-box 和标准 URI。"""

    node = _make_node(
        name="AnyTLS-01",
        node_type="anytls",
        server="anytls.example.com",
        port=443,
        password="anytls-password",
        sni="anytls.example.com",
        fingerprint="chrome",
        security="tls",
        tls=True,
    )
    clash = yaml.safe_load(ClashExporter().export([(node, node.name)]))
    proxy = clash["proxies"][0]
    assert proxy["type"] == "anytls"
    assert proxy["password"] == "anytls-password"

    from app.exporters.singbox import SingboxExporter
    from app.exporters.uri import UriExporter

    singbox = json.loads(SingboxExporter().export([(node, node.name)]))
    outbound = next(item for item in singbox["outbounds"] if item["tag"] == node.name)
    assert outbound["type"] == "anytls"
    assert outbound["tls"]["enabled"] is True
    assert UriExporter().export([(node, node.name)]).startswith("anytls://")


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


def test_export_yaml_is_valid_mihomo_config() -> None:
    """生成的 YAML 应能被安全解析，且 proxies 字段满足 Mihomo 基本结构。"""

    nodes = [
        _make_node(
            name="HK-01",
            node_type="vless",
            server="hk.example.com",
            port=443,
            uuid="uuid-1",
            network="tcp",
            tls=True,
            sni="hk.example.com",
            fingerprint="chrome",
            public_key="pbk",
            short_id="sid",
        ),
        _make_node(
            name="JP-SS",
            node_type="shadowsocks",
            server="jp.example.com",
            port=8388,
            password="password-1",
            cipher="aes-256-gcm",
        ),
    ]
    yaml_text = ClashExporter().export([(nodes[0], "HK-01"), (nodes[1], "JP-SS")])
    data = yaml.safe_load(yaml_text)
    assert isinstance(data, dict)
    assert isinstance(data["proxies"], list)
    assert len(data["proxies"]) == 2
    for proxy in data["proxies"]:
        assert proxy["name"]
        assert proxy["type"] in ("vless", "ss")
        assert proxy["server"]
        assert isinstance(proxy["port"], int)
        if proxy["type"] == "vless":
            assert proxy["uuid"]
            assert proxy["network"] in ("tcp", "ws")
            assert isinstance(proxy["tls"], bool)
            assert proxy["udp"] is True
        else:
            assert proxy["cipher"]
            assert proxy["password"]
            assert proxy["udp"] is True


def test_export_makes_duplicate_names_unique() -> None:
    """Clash group 引用的代理名称必须唯一。"""

    nodes = [
        _make_node(
            name="same",
            node_type="vless",
            server="same-a.example.com",
            port=443,
            uuid="uuid-same-a",
        ),
        _make_node(
            name="same",
            node_type="vless",
            server="same-b.example.com",
            port=443,
            uuid="uuid-same-b",
        ),
    ]
    data = yaml.safe_load(ClashExporter().export([(nodes[0], "same"), (nodes[1], "same")]))
    proxy_names = [proxy["name"] for proxy in data["proxies"]]
    assert proxy_names == ["same", "same-2"]
    assert data["proxy-groups"][0]["proxies"] == proxy_names


def test_export_vmess_trojan_socks_http() -> None:
    """新协议节点应输出 Mihomo 可识别的代理配置。"""

    nodes = [
        _make_node(
            name="VM-01",
            node_type="vmess",
            server="vm.example.com",
            port=443,
            uuid="uuid-vm",
            network="ws",
            path="/vm",
            host="vm.example.com",
            tls=True,
            sni="vm.example.com",
            metadata_json={"aid": 0},
        ),
        _make_node(
            name="TR-01",
            node_type="trojan",
            server="tr.example.com",
            port=443,
            password="tr-pass",
            tls=True,
            sni="tr.example.com",
        ),
        _make_node(
            name="SK-01",
            node_type="socks",
            server="sk.example.com",
            port=1080,
            username="sk-user",
            password="sk-pass",
        ),
        _make_node(
            name="HP-01",
            node_type="http",
            server="hp.example.com",
            port=8080,
            username="hp-user",
            password="hp-pass",
        ),
    ]
    items = [(node, node.name) for node in nodes]
    data = yaml.safe_load(ClashExporter().export(items))
    proxies = {proxy["name"]: proxy for proxy in data["proxies"]}
    assert proxies["VM-01"]["type"] == "vmess"
    assert proxies["VM-01"]["uuid"] == "uuid-vm"
    assert proxies["TR-01"]["type"] == "trojan"
    assert proxies["TR-01"]["password"] == "tr-pass"
    assert proxies["SK-01"]["type"] == "socks5"
    assert proxies["SK-01"]["username"] == "sk-user"
    assert proxies["HP-01"]["type"] == "http"
    assert proxies["HP-01"]["username"] == "hp-user"
