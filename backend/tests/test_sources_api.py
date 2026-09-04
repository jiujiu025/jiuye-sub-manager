"""上游订阅 REST API 测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.node import Node
from app.models.package import Package, PackageRule
from app.models.source import Source
from app.schemas.source import SyncResult
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


def test_sources_require_auth(client: TestClient) -> None:
    """未登录访问订阅接口应返回 401。"""

    response = client.get("/api/sources")
    assert response.status_code == 401


def test_source_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    """上游订阅增删改查完整流程。"""

    create_response = client.post(
        "/api/sources",
        json={
            "name": "airport_api",
            "url": "https://example.com/sub",
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    source_id = create_response.json()["id"]
    assert create_response.json()["url"] == "https://example.com/sub"

    db = SessionLocal()
    try:
        node = Node(
            source_id=source_id,
            source_name="airport_api",
            original_name="airport-api-node",
            name="airport-api-node",
            type="vless",
            server="airport-api.example.com",
            port=443,
            uuid="airport-api-uuid",
            node_fingerprint=build_node_fingerprint(
                node_type="vless",
                server="airport-api.example.com",
                port=443,
                uuid="airport-api-uuid",
            ),
        )
        package = Package(
            name="airport-api-package",
            enabled=True,
            token_hash="airport-api-package-hash",
            token_prefix="airport-a",
        )
        db.add_all([node, package])
        db.flush()
        db.add(PackageRule(package_id=package.id, source_filter=["airport_api"]))
        db.commit()
        package_id = package.id
    finally:
        db.close()

    list_response = client.get("/api/sources", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1
    assert list_response.json()["items"][0]["url_masked"]
    assert "url" not in list_response.json()["items"][0]

    update_response = client.put(
        f"/api/sources/{source_id}",
        json={"name": "airport_api_renamed"},
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "airport_api_renamed"

    db = SessionLocal()
    try:
        renamed_node = db.scalar(select(Node).where(Node.source_id == source_id))
        assert renamed_node is not None
        assert renamed_node.source_name == "airport_api_renamed"
        rule = db.scalar(select(PackageRule).where(PackageRule.package_id == package_id))
        assert rule is not None
        assert rule.source_filter == ["airport_api_renamed"]
    finally:
        db.close()

    delete_response = client.delete(f"/api/sources/{source_id}", headers=auth_headers)
    assert delete_response.status_code == 204
    get_response = client.get(f"/api/sources/{source_id}", headers=auth_headers)
    assert get_response.status_code == 404


def test_create_source_invalid_url(client: TestClient, auth_headers: dict[str, str]) -> None:
    """非法 URL 应返回 400。"""

    response = client.post(
        "/api/sources",
        json={"name": "bad_url", "url": "not-a-url"},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_manual_sync(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """手动同步接口应返回同步结果。"""

    db = SessionLocal()
    try:
        source = Source(
            name="airport_manual",
            url="https://example.com/sub",
            enabled=True,
            format="auto",
        )
        db.add(source)
        db.commit()
        source_id = source.id
    finally:
        db.close()

    def fake_sync(self, source):
        return SyncResult(
            source_id=source.id,
            source_name=source.name,
            status="success",
            node_count=2,
            added_count=2,
            removed_count=0,
            changed_count=0,
            version=1,
        )

    monkeypatch.setattr("app.services.sync_service.SyncService.sync_source", fake_sync)
    response = client.post(f"/api/sources/{source_id}/sync", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["node_count"] == 2
