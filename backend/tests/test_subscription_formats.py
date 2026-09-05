"""订阅兼容层的格式、筛选和异常节点回归测试。"""

from __future__ import annotations

import base64
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models.node import Node
from app.utils.fingerprint import build_node_fingerprint


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _add_node(db, *, name: str, node_type: str, server: str, **fields) -> Node:
    port = fields.pop("port", 443)
    node = Node(
        source_id=None,
        source_name="兼容层自有节点",
        original_name=name,
        name=name,
        type=node_type,
        server=server,
        port=port,
        node_fingerprint=build_node_fingerprint(
            node_type=node_type,
            server=server,
            port=port,
            uuid=fields.get("uuid"),
            password=fields.get("password"),
            cipher=fields.get("cipher"),
        ),
        **fields,
    )
    db.add(node)
    return node


def _create_package(
    client: TestClient, headers: dict, name: str, rules: dict | None = None
) -> str:
    response = client.post(
        "/api/packages",
        json={"name": name, "rules": rules or {}},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["token"]


def test_subscription_formats_and_cache_are_isolated(
    client: TestClient, auth_headers: dict
) -> None:
    """同一 Token 的四种输出均有效，且不会互相复用缓存。"""

    db = SessionLocal()
    try:
        nodes = [
            _add_node(
            db,
            name="香港 TLS",
            node_type="vless",
            server="hk-tls.example.com",
            uuid="11111111-1111-4111-8111-111111111111",
            network="tcp",
            security="tls",
            tls=True,
            sni="hk-tls.example.com",
            country="香港",
            ),
            _add_node(
            db,
            name="日本 Reality WS",
            node_type="vless",
            server="jp-reality.example.com",
            uuid="22222222-2222-4222-8222-222222222222",
            network="ws",
            security="reality",
            tls=True,
            sni="reality.example.com",
            fingerprint="chrome",
            public_key="public-key",
            short_id="short-id",
            path="/ws",
            host="cdn.example.com",
            country="日本",
            ),
            _add_node(
            db,
            name="美国 SS",
            node_type="shadowsocks",
            server="us-ss.example.com",
            port=8388,
            password="ss-password",
            cipher="aes-256-gcm",
            country="美国",
            ),
            _add_node(
            db,
            name="英国 VMess",
            node_type="vmess",
            server="uk-vmess.example.com",
            uuid="33333333-3333-4333-8333-333333333333",
            network="ws",
            tls=True,
            sni="uk-vmess.example.com",
            path="/vmess",
            host="uk-vmess.example.com",
            metadata_json={"aid": 0},
            country="英国",
            ),
            _add_node(
            db,
            name="法国 Trojan",
            node_type="trojan",
            server="fr-trojan.example.com",
            password="trojan-password",
            tls=True,
            sni="fr-trojan.example.com",
            country="法国",
            ),
        ]
        db.commit()
        node_ids = [node.id for node in nodes]
    finally:
        db.close()

    token = _create_package(
        client, auth_headers, "兼容层多格式套餐", {"node_ids": node_ids}
    )
    clash = client.get(f"/sub/{token}?client=clash")
    assert clash.status_code == 200
    assert clash.headers["content-type"].startswith("application/yaml")
    clash_data = yaml.safe_load(clash.text)
    assert len(clash_data["proxies"]) == 5
    assert clash_data["proxies"][0]["tls"] is True
    assert clash_data["proxy-groups"][0]["proxies"] == [
        proxy["name"] for proxy in clash_data["proxies"]
    ]
    assert clash_data["rules"] == ["MATCH,Proxy"]
    reality = next(proxy for proxy in clash_data["proxies"] if proxy["name"] == "日本 Reality WS")
    assert reality["tls"] is True
    assert reality["reality-opts"]["public-key"] == "public-key"
    assert reality["ws-opts"]["headers"]["Host"] == "cdn.example.com"

    mihomo = client.get(f"/sub/{token}?client=mihomo")
    assert mihomo.status_code == 200
    assert mihomo.headers["content-type"].startswith("application/yaml")
    assert len(yaml.safe_load(mihomo.text)["proxies"]) == 5

    singbox = client.get(f"/sub/{token}?client=singbox")
    assert singbox.status_code == 200
    assert singbox.headers["content-type"].startswith("application/json")
    singbox_data = json.loads(singbox.text)
    outbounds = {item["tag"]: item for item in singbox_data["outbounds"]}
    assert len(outbounds) == 7
    assert outbounds["日本 Reality WS"]["tls"]["reality"]["public_key"] == "public-key"
    assert outbounds["日本 Reality WS"]["transport"]["headers"]["Host"] == "cdn.example.com"

    uri = client.get(f"/sub/{token}?client=uri")
    assert uri.status_code == 200
    assert uri.headers["content-type"].startswith("text/plain")
    lines = uri.text.strip().splitlines()
    assert len(lines) == 5
    assert sum(line.startswith(prefix) for line in lines for prefix in ("vless://", "ss://", "vmess://", "trojan://")) == 5
    ss_line = next(line for line in lines if line.startswith("ss://"))
    encoded = ss_line.removeprefix("ss://").split("@", 1)[0]
    decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    assert decoded == "aes-256-gcm:ss-password"


def test_subscription_filters_apply_to_all_formats(
    client: TestClient, auth_headers: dict
) -> None:
    """国家、包含关键词和排除关键词在兼容层中仍由套餐规则控制。"""

    db = SessionLocal()
    try:
        nodes = [
            _add_node(
            db,
            name="筛选 香港 保留",
            node_type="vless",
            server="filter-hk.example.com",
            uuid="44444444-4444-4444-8444-444444444444",
            country="香港",
            ),
            _add_node(
            db,
            name="筛选 香港 排除",
            node_type="vless",
            server="filter-hk-excluded.example.com",
            uuid="55555555-5555-4555-8555-555555555555",
            country="香港",
            ),
            _add_node(
            db,
            name="筛选 日本",
            node_type="vless",
            server="filter-jp.example.com",
            uuid="66666666-6666-4666-8666-666666666666",
            country="日本",
            ),
        ]
        db.commit()
        node_ids = [node.id for node in nodes]
    finally:
        db.close()

    token = _create_package(
        client,
        auth_headers,
        "兼容层筛选套餐",
        {
            "node_ids": node_ids,
            "country_filter": ["香港"],
            "include_keywords": ["保留"],
            "exclude_keywords": ["排除"],
        },
    )
    for output_format in ("clash", "mihomo", "singbox"):
        response = client.get(f"/sub/{token}?client={output_format}")
        assert response.status_code == 200
        if output_format == "singbox":
            assert len(json.loads(response.text)["outbounds"]) == 3
        else:
            assert len(yaml.safe_load(response.text)["proxies"]) == 1
    uri = client.get(f"/sub/{token}?client=uri")
    assert len(uri.text.strip().splitlines()) == 1
    assert "filter-hk.example.com" in uri.text
    assert "filter-hk-excluded.example.com" not in uri.text


def test_subscription_ignores_invalid_nodes_without_returning_500(
    client: TestClient, auth_headers: dict
) -> None:
    """数据库中单个异常节点不能阻断同套餐内的合法节点。"""

    db = SessionLocal()
    try:
        nodes = [
            _add_node(
            db,
            name="合法节点",
            node_type="vless",
            server="valid-format.example.com",
            uuid="77777777-7777-4777-8777-777777777777",
            ),
            _add_node(
            db,
            name="异常节点",
            node_type="vless",
            server="invalid-format.example.com",
            uuid=None,
            ),
        ]
        db.commit()
        node_ids = [node.id for node in nodes]
    finally:
        db.close()

    token = _create_package(
        client, auth_headers, "兼容层异常节点套餐", {"node_ids": node_ids}
    )
    response = client.get(f"/sub/{token}?client=singbox")
    assert response.status_code == 200
    assert len(json.loads(response.text)["outbounds"]) == 3


def test_subscription_client_user_agent_and_invalid_client(
    client: TestClient, auth_headers: dict
) -> None:
    """未指定格式时按 User-Agent 识别，未知格式返回明确错误。"""

    db = SessionLocal()
    try:
        node = _add_node(
            db,
            name="UA 节点",
            node_type="vless",
            server="ua-format.example.com",
            uuid="88888888-8888-4888-8888-888888888888",
        )
        db.commit()
        node_id = node.id
    finally:
        db.close()
    token = _create_package(
        client, auth_headers, "兼容层 UA 套餐", {"node_ids": [node_id]}
    )
    response = client.get(f"/sub/{token}", headers={"User-Agent": "sing-box/1.10"})
    assert response.headers["content-type"].startswith("application/json")
    assert client.get(f"/sub/{token}?client=unknown").status_code == 400
