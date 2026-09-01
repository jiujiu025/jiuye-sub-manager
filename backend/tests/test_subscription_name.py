"""订阅显示名称 subscription_name 功能测试。"""

from __future__ import annotations

import pytest
import yaml
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


def _create_package(client, headers, name, **extra):
    response = client.post(
        "/api/packages",
        json={"name": name, **extra},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def _add_node(db, *, server: str, name: str, uuid: str) -> None:
    db.add(
        Node(
            source_id=None,
            source_name="自有节点",
            original_name=name,
            name=name,
            type="vless",
            server=server,
            port=443,
            uuid=uuid,
            country="香港",
            source_type="custom",
            source_subtype="custom_manual",
            node_fingerprint=build_node_fingerprint(
                node_type="vless", server=server, port=443, uuid=uuid
            ),
        )
    )


def test_create_with_subscription_name(client: TestClient, auth_headers: dict) -> None:
    payload = _create_package(
        client, auth_headers, "订阅名套餐A", subscription_name="我的订阅A"
    )
    assert payload["name"] == "订阅名套餐A"
    assert payload["subscription_name"] == "我的订阅A"


def test_create_fallback_to_package_name(client: TestClient, auth_headers: dict) -> None:
    payload = _create_package(client, auth_headers, "订阅名套餐B")
    assert payload["subscription_name"] == "订阅名套餐B"


def test_update_subscription_name_keeps_token_and_url(
    client: TestClient, auth_headers: dict
) -> None:
    payload = _create_package(
        client, auth_headers, "订阅名套餐C", subscription_name="旧显示名"
    )
    package_id = payload["id"]
    url_before = payload["subscription_url"]

    db = SessionLocal()
    try:
        stored_before = db.scalar(select(Package).where(Package.id == package_id))
        token_hash_before = stored_before.token_hash
        token_encrypted_before = stored_before.token_encrypted
    finally:
        db.close()

    update = client.put(
        f"/api/packages/{package_id}",
        json={"subscription_name": "新显示名"},
        headers=auth_headers,
    )
    assert update.status_code == 200
    assert update.json()["subscription_name"] == "新显示名"

    db = SessionLocal()
    try:
        stored_after = db.scalar(select(Package).where(Package.id == package_id))
        assert stored_after.token_hash == token_hash_before
        assert stored_after.token_encrypted == token_encrypted_before
    finally:
        db.close()

    list_response = client.get("/api/packages", headers=auth_headers).json()
    item = next(item for item in list_response if item["id"] == package_id)
    assert item["subscription_url"] == url_before


def test_update_package_name_keeps_url(client: TestClient, auth_headers: dict) -> None:
    payload = _create_package(client, auth_headers, "订阅名套餐D")
    package_id = payload["id"]
    url_before = payload["subscription_url"]

    update = client.put(
        f"/api/packages/{package_id}",
        json={"name": "订阅名套餐D改名"},
        headers=auth_headers,
    )
    assert update.status_code == 200

    list_response = client.get("/api/packages", headers=auth_headers).json()
    item = next(item for item in list_response if item["id"] == package_id)
    assert item["subscription_url"] == url_before


def test_clash_output_uses_subscription_name_without_touching_node_names(
    client: TestClient, auth_headers: dict
) -> None:
    db = SessionLocal()
    try:
        _add_node(
            db,
            server="subname-test.example.com",
            name="订阅测试节点",
            uuid="subname-test-uuid",
        )
        db.commit()
    finally:
        db.close()

    payload = _create_package(
        client,
        auth_headers,
        "套餐显示名",
        subscription_name="我的订阅显示名",
        rules={
            "source_filter": ["自有节点"],
            "include_keywords": ["订阅测试"],
            "rename_rules": [{"replacements": [{"from": "订阅测试", "to": "RENAMED"}]}],
        },
    )
    token = payload["token"]
    response = client.get(f"/sub/{token}")
    assert response.status_code == 200
    data = yaml.safe_load(response.text)
    assert data["sub-name"] == "我的订阅显示名"
    proxies = data["proxies"]
    target = [proxy for proxy in proxies if proxy["server"] == "subname-test.example.com"]
    assert target
    assert target[0]["name"] == "RENAMED节点"
    assert all(proxy["name"] != "我的订阅显示名" for proxy in proxies)


def test_legacy_package_with_null_subscription_name(
    client: TestClient, auth_headers: dict
) -> None:
    db = SessionLocal()
    try:
        _add_node(
            db,
            server="legacy-subname-test.example.com",
            name="旧套餐节点",
            uuid="legacy-subname-uuid",
        )
        db.commit()
    finally:
        db.close()

    payload = _create_package(
        client,
        auth_headers,
        "旧套餐名称",
        rules={"include_keywords": ["旧套餐节点"]},
    )
    package_id = payload["id"]
    token = payload["token"]

    # 模拟迁移前的旧套餐：subscription_name 为空
    db = SessionLocal()
    try:
        package = db.scalar(select(Package).where(Package.id == package_id))
        package.subscription_name = None
        db.commit()
    finally:
        db.close()

    list_response = client.get("/api/packages", headers=auth_headers).json()
    item = next(item for item in list_response if item["id"] == package_id)
    assert item["subscription_name"] == "旧套餐名称"

    response = client.get(f"/sub/{token}")
    assert response.status_code == 200
    data = yaml.safe_load(response.text)
    assert data["sub-name"] == "旧套餐名称"
