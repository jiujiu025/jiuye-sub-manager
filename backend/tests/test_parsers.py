"""订阅解析器单元测试。"""

from __future__ import annotations

import base64
import json

import pytest

from app.parsers.base import ParseError
from app.parsers.detector import detect_format
from app.parsers.factory import parse_content
from app.parsers.ss_parser import parse_ss_uri
from app.parsers.vless_parser import parse_vless_uri
from app.parsers.vmess_parser import parse_vmess_uri
from app.parsers.anytls_parser import parse_anytls_uri
from app.utils.country import detect_country


def test_parse_vless_uri() -> None:
    """VLESS URI 应解析出全部关键字段并识别国家。"""

    uri = (
        "vless://abc-123@example.com:443"
        "?security=reality&sni=example.com&fp=chrome&pbk=pubkey&sid=shortid&type=tcp"
        "#%E9%A6%99%E6%B8%AF01"
    )
    node = parse_vless_uri(uri)
    assert node.type == "vless"
    assert node.server == "example.com"
    assert node.port == 443
    assert node.uuid == "abc-123"
    assert node.security == "reality"
    assert node.sni == "example.com"
    assert node.fingerprint == "chrome"
    assert node.public_key == "pubkey"
    assert node.short_id == "shortid"
    assert node.original_name == "香港01"
    assert node.country == "香港"


def test_parse_vless_tls_security_enables_tls() -> None:
    """VLESS security=tls 应被识别为 TLS，且不依赖显式 tls 参数。"""

    node = parse_vless_uri(
        "vless://uuid-tls@tls.example.com:443?security=tls&sni=tls.example.com"
    )
    assert node.security == "tls"
    assert node.tls is True


@pytest.mark.parametrize(
    ("name", "country"),
    [
        ("RUS-01", None),
        ("asus-home-01", None),
        ("US-01", "美国"),
        ("JP Tokyo 01", "日本"),
    ],
)
def test_detect_country_does_not_match_embedded_abbreviations(
    name: str, country: str | None
) -> None:
    """国家缩写必须按独立词匹配，不能命中普通单词中的子串。"""

    assert detect_country(name) == country


def test_parse_vless_reality_security_is_case_insensitive() -> None:
    """VLESS Reality 的 security 大小写不应改变 Reality 判定。"""

    node = parse_vless_uri(
        "vless://uuid-reality@reality.example.com:443?security=Reality&pbk=key"
    )
    assert node.security == "reality"
    assert node.tls is True


def test_parse_ss_uri_sip002() -> None:
    """SIP002 格式 SS URI 应正确解码 Base64 的 method:password。"""

    userinfo = base64.urlsafe_b64encode(b"aes-256-gcm:password").decode("ascii")
    node = parse_ss_uri(f"ss://{userinfo}@server.example:8388#US-SS")
    assert node.type == "shadowsocks"
    assert node.server == "server.example"
    assert node.port == 8388
    assert node.cipher == "aes-256-gcm"
    assert node.password == "password"
    assert node.original_name == "US-SS"
    assert node.country == "美国"


def test_parse_ss_uri_legacy() -> None:
    """旧式明文 method:password 格式也应兼容。"""

    node = parse_ss_uri("ss://aes-256-gcm:password@server.example:8388#%E6%97%A5%E6%9C%AC01")
    assert node.cipher == "aes-256-gcm"
    assert node.password == "password"
    assert node.original_name == "日本01"
    assert node.country == "日本"


def test_parse_ss_uri_sip002_whole_authority_base64() -> None:
    """标准 SIP002 应支持将完整 method:password@host:port 编码。"""

    encoded = base64.urlsafe_b64encode(
        b"aes-256-gcm:password@server.example:8388"
    ).decode("ascii").rstrip("=")
    node = parse_ss_uri(f"ss://{encoded}#US-SIP002")
    assert node.cipher == "aes-256-gcm"
    assert node.password == "password"
    assert node.server == "server.example"
    assert node.port == 8388
    assert node.original_name == "US-SIP002"


def test_parse_anytls_uri() -> None:
    """AnyTLS URI 应解析密码、TLS、SNI 和指纹。"""

    node = parse_anytls_uri(
        "anytls://p%40ss@anytls.example.com:443"
        "?security=tls&sni=anytls.example.com&fp=chrome#AnyTLS-01"
    )
    assert node.type == "anytls"
    assert node.password == "p@ss"
    assert node.server == "anytls.example.com"
    assert node.port == 443
    assert node.security == "tls"
    assert node.tls is True
    assert node.sni == "anytls.example.com"
    assert node.fingerprint == "chrome"


def test_parse_clash_anytls() -> None:
    """Clash/Mihomo AnyTLS 节点应进入统一解析结构。"""

    nodes = parse_content(
        """
proxies:
  - name: AnyTLS-01
    type: anytls
    server: anytls.example.com
    port: 443
    password: anytls-password
    sni: anytls.example.com
    client-fingerprint: chrome
""",
        "clash",
    )
    assert len(nodes) == 1
    assert nodes[0].type == "anytls"
    assert nodes[0].password == "anytls-password"
    assert nodes[0].tls is True


def test_parse_base64_subscription() -> None:
    """Base64 订阅应自动检测并解析全部有效节点。"""

    lines = [
        "vless://uuid-a@hk.example.com:443?security=reality&sni=hk.example.com#%E9%A6%99%E6%B8%AF01",
        "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@jp.example.com:8388#%E6%97%A5%E6%9C%AC01",
    ]
    payload = base64.b64encode("\n".join(lines).encode("utf-8")).decode("ascii")
    assert detect_format(payload) == "base64"
    nodes = parse_content(payload)
    assert len(nodes) == 2
    assert {node.type for node in nodes} == {"vless", "shadowsocks"}


def test_parse_vmess_v2ray_share_link_urlsafe_without_padding() -> None:
    """V2Ray 常见 URL-safe、无填充 VMess 链接应能导入。"""

    payload = {
        "v": "2",
        "ps": "日本 VMess",
        "add": "jp-v2ray.example.com",
        "port": "443",
        "id": "00000000-0000-0000-0000-000000000001",
        "net": "ws",
        "host": "cdn.example.com",
        "path": "/v2ray",
        "tls": "tls",
        "sni": "jp-v2ray.example.com",
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    node = parse_vmess_uri(f"vmess://{encoded}")
    assert node.server == "jp-v2ray.example.com"
    assert node.port == 443
    assert node.network == "ws"
    assert node.tls is True
    assert node.host == "cdn.example.com"
    assert node.path == "/v2ray"


def test_parse_escaped_vmess_scheme() -> None:
    """复制自 Markdown 或日志的转义协议前缀也应能识别。"""

    payload = {"add": "escaped.example.com", "port": 443, "id": "uuid-escaped"}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    nodes = parse_content(f"vmess\\://{encoded}")
    assert len(nodes) == 1
    assert nodes[0].type == "vmess"


def test_parse_vmess_invalid_port_is_parse_error() -> None:
    """非法 VMess 端口必须转成业务解析错误。"""

    payload = {"add": "bad.example.com", "port": "bad", "id": "uuid"}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(ParseError, match="端口"):
        parse_vmess_uri(f"vmess://{encoded}")


def test_parse_vmess_missing_uuid_is_parse_error() -> None:
    """缺少 VMess 用户 ID 的配置不能被导入。"""

    payload = {"add": "missing-uuid.example.com", "port": 443}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(ParseError, match="UUID"):
        parse_vmess_uri(f"vmess://{encoded}")


def test_parse_v2ray_json_vmess() -> None:
    """常见 V2Ray outbounds.vnext 配置应能转换为 VMess 节点。"""

    content = json.dumps(
        {
            "outbounds": [
                {
                    "tag": "V2Ray JP",
                    "protocol": "vmess",
                    "settings": {
                        "vnext": [
                            {
                                "address": "jp-json.example.com",
                                "port": 443,
                                "users": [{"id": "uuid-json", "alterId": 0}],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "ws",
                        "security": "tls",
                        "tlsSettings": {"serverName": "jp-json.example.com"},
                        "wsSettings": {"path": "/ws", "headers": {"Host": "cdn.example.com"}},
                    },
                }
            ]
        }
    )
    assert detect_format(content) == "v2ray-json"
    nodes = parse_content(content)
    assert len(nodes) == 1
    assert nodes[0].type == "vmess"
    assert nodes[0].tls is True
    assert nodes[0].path == "/ws"
    assert nodes[0].host == "cdn.example.com"


def test_parse_v2ray_json_bom_reality_and_vmess_fields() -> None:
    """带 BOM 的 V2Ray 配置应保留 Reality、WS 和 VMess 用户参数。"""

    content = "\ufeff" + json.dumps(
        {
            "outbounds": [
                {
                    "tag": "VLESS Reality",
                    "protocol": "vless",
                    "settings": {
                        "vnext": [
                            {
                                "address": "reality.example.com",
                                "port": "443",
                                "users": [{"id": "uuid-reality", "flow": "xtls-rprx-vision"}],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "ws",
                        "security": "reality",
                        "realitySettings": {
                            "serverName": "sni.example.com",
                            "fingerprint": "chrome",
                            "publicKey": "public-key",
                            "shortId": "short-id",
                        },
                        "wsSettings": {
                            "path": "/reality",
                            "headers": {"hOsT": "cdn.example.com"},
                        },
                    },
                },
                {
                    "tag": "VMess",
                    "protocol": "vmess",
                    "settings": {
                        "vnext": [
                            {
                                "address": "vmess.example.com",
                                "port": 443,
                                "users": [{"id": "uuid-vmess", "alterId": 4, "security": "chacha20-poly1305"}],
                            }
                        ]
                    },
                    "streamSettings": {"network": "tcp", "security": "tls"},
                },
            ]
        }
    )
    assert detect_format(content) == "v2ray-json"
    nodes = parse_content(content)
    assert len(nodes) == 2
    reality, vmess = nodes
    assert (reality.tls, reality.sni, reality.public_key, reality.short_id) == (
        True, "sni.example.com", "public-key", "short-id"
    )
    assert (reality.host, reality.path, reality.metadata["flow"]) == (
        "cdn.example.com", "/reality", "xtls-rprx-vision"
    )
    assert (vmess.cipher, vmess.metadata["aid"], vmess.tls) == (
        "chacha20-poly1305", 4, True
    )


def test_parse_v2ray_json_single_outbound_and_servers() -> None:
    """单个 V2Ray outbound 及 shadowsocks servers 写法应能导入。"""

    content = json.dumps(
        {
            "protocol": "shadowsocks",
            "tag": "SS JSON",
            "settings": {
                "servers": [
                    {
                        "address": "ss.example.com",
                        "port": "8388",
                        "method": "aes-256-gcm",
                        "password": "secret",
                    }
                ]
            },
        }
    )
    assert detect_format(content) == "v2ray-json"
    nodes = parse_content(content, "v2ray")
    assert len(nodes) == 1
    assert (nodes[0].type, nodes[0].cipher, nodes[0].password) == (
        "shadowsocks", "aes-256-gcm", "secret"
    )


def test_parse_clash_yaml() -> None:
    """Clash YAML 应解析 proxies 中的 vless 与 shadowsocks 节点。"""

    content = """
proxies:
  - name: HK-01
    type: vless
    server: hk.example.com
    port: 443
    uuid: uuid-1
    network: tcp
    security: reality
    tls: true
    sni: hk.example.com
    client-fingerprint: chrome
    public-key: pbk
    short-id: sid
  - name: JP-SS
    type: shadowsocks
    server: jp.example.com
    port: 8388
    cipher: aes-256-gcm
    password: secret
"""
    assert detect_format(content) == "clash"
    nodes = parse_content(content)
    assert len(nodes) == 2
    assert nodes[0].type == "vless"
    assert nodes[0].country == "香港"
    assert nodes[1].type == "shadowsocks"


def test_parse_clash_mihomo_protocol_and_nested_transport_fields() -> None:
    """Clash/Mihomo 常见协议及嵌套 Reality/WebSocket 字段应映射到统一结构。"""

    content = """
proxies:
  - name: HK-Reality-WS
    type: vless
    server: hk.example.com
    port: 443
    uuid: uuid-reality
    network: ws
    security: reality
    tls: true
    servername: hk.example.com
    client-fingerprint: chrome
    reality-opts:
      public-key: public-key-value
      short-id: short-id-value
    ws-opts:
      path: /reality
      headers:
        Host: cdn.example.com
  - name: VM-JP
    type: vmess
    server: jp.example.com
    port: 443
    uuid: uuid-vmess
    alterId: 2
    cipher: auto
    network: ws
    tls: true
    servername: jp.example.com
    ws-opts:
      path: /vmess
      headers:
        Host: vm.example.com
  - name: US-Trojan
    type: trojan
    server: us.example.com
    port: 443
    password: trojan-password
    servername: us.example.com
    fingerprint: chrome
    ws-opts:
      path: /trojan
      headers:
        Host: tr.example.com
  - name: SG-SS
    type: ss
    server: sg.example.com
    port: 8388
    cipher: aes-256-gcm
    password: ss-password
"""
    nodes = parse_content(content, "clash")
    assert [node.type for node in nodes] == [
        "vless", "vmess", "trojan", "shadowsocks"
    ]
    reality, vmess, trojan, shadowsocks = nodes
    assert (reality.tls, reality.security, reality.public_key, reality.short_id) == (
        True, "reality", "public-key-value", "short-id-value"
    )
    assert (reality.sni, reality.path, reality.host, reality.fingerprint) == (
        "hk.example.com", "/reality", "cdn.example.com", "chrome"
    )
    assert (vmess.uuid, vmess.path, vmess.host, vmess.tls) == (
        "uuid-vmess", "/vmess", "vm.example.com", True
    )
    assert vmess.metadata["alterId"] == 2
    assert (trojan.password, trojan.sni, trojan.path, trojan.host) == (
        "trojan-password", "us.example.com", "/trojan", "tr.example.com"
    )
    assert trojan.tls is True
    assert (shadowsocks.cipher, shadowsocks.password) == (
        "aes-256-gcm", "ss-password"
    )


def test_parse_clash_vless_security_tls_enables_tls() -> None:
    """Clash/Mihomo 的 VLESS security=tls 应推导出 tls=true。"""

    nodes = parse_content(
        """
proxies:
  - name: TLS-VLESS
    type: vless
    server: tls.example.com
    port: 443
    uuid: uuid-tls
    security: tls
""",
        "clash",
    )
    assert len(nodes) == 1
    assert nodes[0].security == "tls"
    assert nodes[0].tls is True


def test_parse_singbox_boolean_tls() -> None:
    """Sing-box 的布尔 TLS 配置应兼容解析。"""

    nodes = parse_content(
        json.dumps(
            {
                "outbounds": [
                    {
                        "type": "vless",
                        "tag": "VLESS TLS",
                        "server": "singbox-tls.example.com",
                        "server_port": 443,
                        "uuid": "uuid-singbox-tls",
                        "tls": True,
                    },
                    {
                        "type": "vless",
                        "tag": "VLESS Plain",
                        "server": "singbox-plain.example.com",
                        "server_port": 80,
                        "uuid": "uuid-singbox-plain",
                        "tls": False,
                    },
                ]
            }
        )
    )
    assert [node.tls for node in nodes] == [True, False]


def test_parse_singbox_rejects_invalid_tls_shape() -> None:
    """非布尔、非对象的 TLS 配置应转换为解析错误。"""

    with pytest.raises(ParseError, match="TLS 配置格式无效"):
        parse_content(
            json.dumps(
                {
                    "outbounds": [
                        {
                            "type": "vless",
                            "server": "invalid-tls.example.com",
                            "server_port": 443,
                            "uuid": "uuid-invalid-tls",
                            "tls": "true",
                        }
                    ]
                }
            )
        )


def test_unknown_content_raises() -> None:
    """无法识别的内容应抛出 ParseError。"""

    assert detect_format("hello world") == "unknown"
    with pytest.raises(ParseError):
        parse_content("hello world")


def test_recursive_parser_failure_is_reported_as_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """异常深度的 YAML/JSON 不得把递归异常冒泡成 500。"""

    monkeypatch.setattr(
        "app.parsers.clash_parser.yaml.safe_load",
        lambda _content: (_ for _ in ()).throw(RecursionError()),
    )
    with pytest.raises(ParseError):
        parse_content("proxies: []", "clash")

    monkeypatch.setattr(
        "app.parsers.v2ray_json_parser.json.loads",
        lambda _content: (_ for _ in ()).throw(RecursionError()),
    )
    with pytest.raises(ParseError):
        parse_content('{"outbounds": []}', "v2ray-json")


def test_uri_lines_ignore_invalid_nodes() -> None:
    """URI 订阅中无法解析的行应被跳过，不影响其他节点。"""

    content = (
        "vless://uuid-a@hk.example.com:443#HK01\n"
        "vmess://bad-line\n"
        "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@jp.example.com:8388#JP01"
    )
    nodes = parse_content(content)
    assert len(nodes) == 2
