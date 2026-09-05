"""套餐 REST API 测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.node import Node
from app.models.package import Package
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


def test_packages_require_auth(client: TestClient) -> None:
    response = client.get("/api/packages")
    assert response.status_code == 401


def test_package_crud_and_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """创建套餐应返回一次明文 Token，数据库只存哈希。"""

    create_response = client.post(
        "/api/packages",
        json={
            "name": "基础套餐",
            "description": "测试套餐",
            "rules": {"country_filter": ["香港"]},
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    package_id = payload["id"]
    token = payload["token"]
    assert len(token) > 32
    assert payload["subscription_url"].endswith(f"/sub/{token}")

    db = SessionLocal()
    try:
        stored = db.scalar(select(Package).where(Package.id == package_id))
        assert stored is not None
        assert stored.token_hash != token
        assert stored.token_hash == __import__("hashlib").sha256(token.encode()).hexdigest()
        assert stored.token_prefix == token[:8]
    finally:
        db.close()

    list_response = client.get("/api/packages", headers=auth_headers)
    assert list_response.status_code == 200
    listed = next(item for item in list_response.json() if item["id"] == package_id)
    assert listed["rules"]["country_filter"] == ["香港"]
    assert listed["rules"]["source_filter"] == []
    assert listed["rules"]["include_keywords"] == []
    assert listed["rules"]["exclude_keywords"] == []
    assert listed["rules"]["rename_rules"] == []
    assert listed["rules"]["sort_rules"] == []
    assert listed["rules"]["node_ids"] == []

    detail_response = client.get(f"/api/packages/{package_id}", headers=auth_headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["rules"]["country_filter"] == ["香港"]

    update_response = client.put(
        f"/api/packages/{package_id}",
        json={"name": "基础套餐改名", "rules": {"country_filter": ["日本"]}},
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "基础套餐改名"
    assert update_response.json()["rules"]["country_filter"] == ["日本"]

    toggle_response = client.post(
        f"/api/packages/{package_id}/toggle", headers=auth_headers
    )
    assert toggle_response.status_code == 200
    assert toggle_response.json()["enabled"] is False

    delete_response = client.delete(f"/api/packages/{package_id}", headers=auth_headers)
    assert delete_response.status_code == 204
    get_response = client.get(f"/api/packages/{package_id}", headers=auth_headers)
    assert get_response.status_code == 404


def test_regenerate_token_invalidates_old_hash(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """重生成 Token 后数据库哈希应改变，旧 Token 立即失效。"""

    create_response = client.post(
        "/api/packages",
        json={"name": "Token 套餐"},
        headers=auth_headers,
    )
    package_id = create_response.json()["id"]
    old_token = create_response.json()["token"]

    regenerate_response = client.post(
        f"/api/packages/{package_id}/regenerate-token", headers=auth_headers
    )
    assert regenerate_response.status_code == 200
    new_token = regenerate_response.json()["token"]
    assert new_token != old_token

    db = SessionLocal()
    try:
        stored = db.scalar(select(Package).where(Package.id == package_id))
        assert stored is not None
        assert stored.token_hash != __import__("hashlib").sha256(old_token.encode()).hexdigest()
        assert stored.token_hash == __import__("hashlib").sha256(new_token.encode()).hexdigest()
    finally:
        db.close()


def test_package_preview_api(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """套餐预览接口应返回应用规则后的节点。"""

    db = SessionLocal()
    try:
        node = Node(
            source_id=None,
            source_name="机场预览A",
            original_name="香港01",
            name="香港01",
            type="vless",
            server="hk.example.com",
            port=443,
            uuid="uuid-preview",
            country="香港",
            node_fingerprint=build_node_fingerprint(
                node_type="vless",
                server="hk.example.com",
                port=443,
                uuid="uuid-preview",
            ),
        )
        db.add(node)
        db.commit()
    finally:
        db.close()

    create_response = client.post(
        "/api/packages",
        json={
            "name": "预览套餐",
            "rules": {
                "source_filter": ["机场预览A"],
                "country_filter": ["香港"],
                "rename_rules": [{"country_abbr": True}],
            },
        },
        headers=auth_headers,
    )
    package_id = create_response.json()["id"]
    preview_response = client.get(
        f"/api/packages/{package_id}/preview", headers=auth_headers
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert len(preview) == 1
    assert preview[0]["name"] == "HK01"
    assert preview[0]["country"] == "香港"


def test_create_package_empty_name_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """套餐名称为空时创建套餐应返回 422。"""

    response = client.post(
        "/api/packages",
        json={"name": ""},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_update_package_rejects_explicit_null_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """套餐名称显式传 null 时应返回业务校验错误。"""

    created = client.post(
        "/api/packages",
        json={"name": "null-package"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    response = client.put(
        f"/api/packages/{created.json()['id']}",
        json={"name": None},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "套餐名称不能为 null"
