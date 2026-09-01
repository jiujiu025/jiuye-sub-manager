"""自有节点导入系统测试。"""

from __future__ import annotations

import base64
import json

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _import(client: TestClient, headers: dict, content: str, subtype: str = "custom_url"):
    return client.post(
        "/api/nodes/import",
        json={"content": content, "source_subtype": subtype, "format": "auto"},
        headers=headers,
    )


def _vmess_uri(server: str = "vmess.example.com", uuid: str = "uuid-vmess") -> str:
    data = {
        "v": "2",
        "ps": "香港VMess",
        "add": server,
        "port": "443",
        "id": uuid,
        "aid": "0",
        "net": "ws",
        "type": "none",
        "host": server,
        "path": "/vmess",
        "tls": "tls",
        "sni": server,
    }
    payload = base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")
    return f"vmess://{payload}"


def test_import_single_vless(client: TestClient, auth_headers: dict) -> None:
    response = _import(client, auth_headers, "vless://uuid-single@single.example.com:443#香港01")
    assert response.status_code == 200
    result = response.json()
    assert result["success"] == 1
    assert result["failed"] == 0
    assert result["total"] == 1

    nodes = client.get("/api/nodes?keyword=single.example.com", headers=auth_headers).json()
    assert nodes["total"] >= 1
    assert nodes["items"][0]["source_type"] == "custom"
    assert nodes["items"][0]["source_subtype"] == "custom_url"


def test_import_batch_vless(client: TestClient, auth_headers: dict) -> None:
    content = "\n".join(
        [
            "vless://uuid-b1@batch1.example.com:443#香港01",
            "vless://uuid-b2@batch2.example.com:443#日本01",
            "vless://uuid-b3@batch3.example.com:443#美国01",
        ]
    )
    result = _import(client, auth_headers, content).json()
    assert result["success"] == 3
    assert result["total"] == 3


def test_import_vmess(client: TestClient, auth_headers: dict) -> None:
    result = _import(client, auth_headers, _vmess_uri()).json()
    assert result["success"] == 1
    nodes = client.get("/api/nodes?node_type=vmess&keyword=vmess.example.com", headers=auth_headers).json()
    assert nodes["total"] >= 1
    assert nodes["items"][0]["uuid_masked"] is not None


def test_import_shadowsocks(client: TestClient, auth_headers: dict) -> None:
    uri = "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@ss-import.example.com:8388#%E6%97%A5%E6%9C%AC01"
    result = _import(client, auth_headers, uri).json()
    assert result["success"] == 1


def test_import_trojan(client: TestClient, auth_headers: dict) -> None:
    uri = "trojan://trojan-pass@trojan-import.example.com:443?security=tls&sni=trojan-import.example.com#%E9%A6%99%E6%B8%AF01"
    result = _import(client, auth_headers, uri).json()
    assert result["success"] == 1
    nodes = client.get("/api/nodes?node_type=trojan&keyword=trojan-import.example.com", headers=auth_headers).json()
    assert nodes["total"] >= 1


def test_import_socks(client: TestClient, auth_headers: dict) -> None:
    uri = "socks5://socks-user:socks-pass@socks-import.example.com:1080#%E7%BE%8E%E5%9B%BD01"
    result = _import(client, auth_headers, uri).json()
    assert result["success"] == 1
    nodes = client.get("/api/nodes?node_type=socks&keyword=socks-import.example.com", headers=auth_headers).json()
    assert nodes["total"] >= 1
    assert nodes["items"][0]["username_masked"] is not None


def test_import_http(client: TestClient, auth_headers: dict) -> None:
    uri = "http://http-user:http-pass@http-import.example.com:8080#%E9%A6%99%E6%B8%AF01"
    result = _import(client, auth_headers, uri).json()
    assert result["success"] == 1
    nodes = client.get("/api/nodes?node_type=http&keyword=http-import.example.com", headers=auth_headers).json()
    assert nodes["total"] >= 1


def test_import_duplicate_node(client: TestClient, auth_headers: dict) -> None:
    uri = "vless://uuid-dup@dup.example.com:443#%E9%A6%99%E6%B8%AF01"
    first = _import(client, auth_headers, uri).json()
    assert first["success"] == 1
    second = _import(client, auth_headers, uri).json()
    assert second["duplicate"] == 1
    assert second["success"] == 0


def test_import_invalid_link_reports_failure(client: TestClient, auth_headers: dict) -> None:
    result = _import(client, auth_headers, "not-a-node-link").json()
    assert result["success"] == 0
    assert result["failed"] == 1
    assert result["failures"][0]["reason"]
    assert "uuid" not in result["failures"][0]["reason"].lower()


def test_import_mixed_protocols(client: TestClient, auth_headers: dict) -> None:
    content = "\n".join(
        [
            "vless://uuid-mix1@mix1.example.com:443#%E9%A6%99%E6%B8%AF01",
            _vmess_uri("mix2.example.com", "uuid-mix2"),
            "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@mix3.example.com:8388#%E6%97%A5%E6%9C%AC01",
            "trojan://mix-pass@mix4.example.com:443#%E7%BE%8E%E5%9B%BD01",
            "socks5://user:pass@mix5.example.com:1080#%E6%96%B0%E5%8A%A0%E5%9D%A101",
            "http://user:pass@mix6.example.com:8080#%E9%9F%A9%E5%9B%BD01",
        ]
    )
    result = _import(client, auth_headers, content).json()
    assert result["success"] == 6
    assert result["failed"] == 0


def test_import_partial_failure(client: TestClient, auth_headers: dict) -> None:
    content = "\n".join(
        [
            "vless://uuid-part@part.example.com:443#%E9%A6%99%E6%B8%AF01",
            "this-is-not-a-valid-link",
        ]
    )
    result = _import(client, auth_headers, content).json()
    assert result["success"] == 1
    assert result["failed"] == 1
    assert result["failures"][0]["index"] == 2


def test_manual_create_vmess_and_trojan(client: TestClient, auth_headers: dict) -> None:
    vmess = client.post(
        "/api/nodes",
        json={
            "name": "手动VMess",
            "type": "vmess",
            "server": "manual-vmess.example.com",
            "port": 443,
            "uuid": "manual-vmess-uuid",
        },
        headers=auth_headers,
    )
    assert vmess.status_code == 201
    assert vmess.json()["source_subtype"] == "custom_manual"

    trojan = client.post(
        "/api/nodes",
        json={
            "name": "手动Trojan",
            "type": "trojan",
            "server": "manual-trojan.example.com",
            "port": 443,
            "password": "manual-trojan-pass",
        },
        headers=auth_headers,
    )
    assert trojan.status_code == 201
    assert trojan.json()["source_subtype"] == "custom_manual"


def test_imported_nodes_work_in_package_and_subscription(
    client: TestClient, auth_headers: dict
) -> None:
    """导入节点应能被套餐筛选并正常生成 Clash/Mihomo。"""

    server = "package-import.example.com"
    _import(client, auth_headers, f"vless://uuid-pkg@{server}:443#%E9%A6%99%E6%B8%AF01")

    package = client.post(
        "/api/packages",
        json={
            "name": "导入节点套餐",
            "rules": {"source_filter": ["自有节点"], "country_filter": ["香港"]},
        },
        headers=auth_headers,
    )
    assert package.status_code == 201
    package_id = package.json()["id"]

    preview = client.get(f"/api/packages/{package_id}/preview", headers=auth_headers).json()
    assert any(item["server"] == server for item in preview)

    subscription_url = package.json()["subscription_url"]
    token = subscription_url.rsplit("/", 1)[-1]
    response = client.get(f"/sub/{token}")
    assert response.status_code == 200
    data = yaml.safe_load(response.text)
    assert "proxies" in data
    assert any(proxy["server"] == server for proxy in data["proxies"])
