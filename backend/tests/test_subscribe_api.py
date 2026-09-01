"""公开订阅接口与端到端验收测试。"""

from __future__ import annotations

import base64

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.node import Node
from app.models.package import Package
from app.models.source import Source
from app.services.sync_service import SyncService
from app.utils.fingerprint import build_node_fingerprint


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _add_node(db, *, name: str, server: str, uuid: str, country: str) -> None:
    node = Node(
        source_id=None,
        source_name="自有节点",
        original_name=name,
        name=name,
        type="vless",
        server=server,
        port=443,
        uuid=uuid,
        country=country,
        node_fingerprint=build_node_fingerprint(
            node_type="vless", server=server, port=443, uuid=uuid
        ),
    )
    db.add(node)


def _subscription_for(client: TestClient, token: str) -> str:
    response = client.get(f"/sub/{token}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/yaml")
    return response.text


def test_invalid_token_returns_404(client: TestClient) -> None:
    """非法 Token 应返回 404。"""

    response = client.get("/sub/not-a-real-token")
    assert response.status_code == 404


def test_disabled_package_returns_403(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """禁用套餐应返回 403。"""

    create_response = client.post(
        "/api/packages", json={"name": "禁用订阅套餐"}, headers=auth_headers
    )
    package_id = create_response.json()["id"]
    token = create_response.json()["token"]
    client.post(f"/api/packages/{package_id}/toggle", headers=auth_headers)

    response = client.get(f"/sub/{token}")
    assert response.status_code == 403


def test_empty_package_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """套餐无节点应返回明确错误而不是损坏配置。"""

    create_response = client.post(
        "/api/packages",
        json={"name": "空订阅套餐", "rules": {"source_filter": ["不存在的来源"]}},
        headers=auth_headers,
    )
    token = create_response.json()["token"]
    response = client.get(f"/sub/{token}")
    assert response.status_code == 404
    assert response.json()["detail"] == "套餐暂无可用节点"


def test_subscription_end_to_end(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """上游修改后再次同步，原订阅 URL 应自动返回新节点。"""

    db = SessionLocal()
    try:
        source = Source(
            name="集成机场",
            url="https://provider.example.com/sub",
            enabled=True,
            allow_empty_override=False,
            format="auto",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        hk_payload = base64.b64encode(
            (
                "vless://uuid-hk@hk-a.example.com:443"
                "?security=reality&sni=hk-a.example.com#%E9%A6%99%E6%B8%AF01"
            ).encode("utf-8")
        ).decode("ascii")
        jp_payload = base64.b64encode(
            (
                "vless://uuid-jp@jp-b.example.com:443"
                "?security=reality&sni=jp-b.example.com#%E6%97%A5%E6%9C%AC01"
            ).encode("utf-8")
        ).decode("ascii")

        SyncService(
            db,
            http_client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, text=hk_payload)
                ),
                timeout=5,
            ),
        ).sync_source(source)
    finally:
        db.close()

    create_response = client.post(
        "/api/packages",
        json={
            "name": "自动更新套餐",
            "rules": {"country_filter": ["香港", "日本"]},
        },
        headers=auth_headers,
    )
    token = create_response.json()["token"]
    subscription_url = create_response.json()["subscription_url"]
    assert subscription_url.endswith(f"/sub/{token}")

    first_response = client.get(f"/sub/{token}")
    assert first_response.status_code == 200
    content_disposition = first_response.headers.get("content-disposition", "")
    assert "sub.yaml" not in content_disposition
    first_yaml = first_response.text
    assert "hk-a.example.com" in first_yaml
    assert "proxy-providers" not in first_yaml
    assert "provider.example.com" not in first_yaml

    # 修改上游内容并再次同步，原 Token/URL 不变
    db = SessionLocal()
    try:
        source = db.scalar(select(Source).where(Source.name == "集成机场"))
        assert source is not None
        SyncService(
            db,
            http_client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, text=jp_payload)
                ),
                timeout=5,
            ),
        ).sync_source(source)
    finally:
        db.close()

    second_yaml = _subscription_for(client, token)
    assert "jp-b.example.com" in second_yaml
    assert "hk-a.example.com" not in second_yaml
    assert "provider.example.com" not in second_yaml


def test_regenerated_token_invalidates_old(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """重生成 Token 后旧 Token 立即失效，新 Token 可用。"""

    db = SessionLocal()
    try:
        _add_node(
            db,
            name="HK-01",
            server="regenerate.example.com",
            uuid="uuid-regenerate",
            country="香港",
        )
        db.commit()
    finally:
        db.close()

    create_response = client.post(
        "/api/packages",
        json={"name": "重生成订阅套餐"},
        headers=auth_headers,
    )
    package_id = create_response.json()["id"]
    old_token = create_response.json()["token"]

    regenerate_response = client.post(
        f"/api/packages/{package_id}/regenerate-token", headers=auth_headers
    )
    new_token = regenerate_response.json()["token"]
    assert new_token != old_token

    old_response = client.get(f"/sub/{old_token}")
    assert old_response.status_code == 404
    new_yaml = _subscription_for(client, new_token)
    assert "regenerate.example.com" in new_yaml
