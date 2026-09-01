"""订阅解析器单元测试。"""

from __future__ import annotations

import base64

import pytest

from app.parsers.base import ParseError
from app.parsers.detector import detect_format
from app.parsers.factory import parse_content
from app.parsers.ss_parser import parse_ss_uri
from app.parsers.vless_parser import parse_vless_uri


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


def test_unknown_content_raises() -> None:
    """无法识别的内容应抛出 ParseError。"""

    assert detect_format("hello world") == "unknown"
    with pytest.raises(ParseError):
        parse_content("hello world")


def test_uri_lines_ignore_invalid_nodes() -> None:
    """URI 订阅中无法解析的行应被跳过，不影响其他节点。"""

    content = (
        "vless://uuid-a@hk.example.com:443#HK01\n"
        "vmess://bad-line\n"
        "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@jp.example.com:8388#JP01"
    )
    nodes = parse_content(content)
    assert len(nodes) == 2
