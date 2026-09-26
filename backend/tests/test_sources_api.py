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
from app.services.subscription_service import SubscriptionService
from app.core.cache import cache_service
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
    db = SessionLocal()
    try:
        deleted_source_rule = db.scalar(
            select(PackageRule).where(PackageRule.package_id == package_id)
        )
        assert deleted_source_rule is not None
        assert deleted_source_rule.source_filter == ["airport_api_renamed"]
    finally:
        db.close()
    get_response = client.get(f"/api/sources/{source_id}", headers=auth_headers)
    assert get_response.status_code == 404


def test_delete_source_invalidates_related_subscription_cache(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """来源删除后，已缓存的套餐不能继续返回已删除节点。"""

    source_response = client.post(
        "/api/sources",
        json={"name": "cache-delete-source", "url": "https://example.com/cache-delete"},
        headers=auth_headers,
    )
    assert source_response.status_code == 201
    source_id = source_response.json()["id"]

    db = SessionLocal()
    try:
        node = Node(
            source_id=source_id,
            source_name="cache-delete-source",
            original_name="缓存删除节点",
            name="缓存删除节点",
            type="vless",
            server="cache-delete.example.com",
            port=443,
            uuid="cache-delete-uuid",
            country="不存在的国家",
            node_fingerprint=build_node_fingerprint(
                node_type="vless",
                server="cache-delete.example.com",
                port=443,
                uuid="cache-delete-uuid",
            ),
        )
        db.add(node)
        db.commit()
        db.refresh(node)
    finally:
        db.close()

    package_response = client.post(
        "/api/packages",
        json={
            "name": "cache-delete-package",
            "rules": {
                "source_filter": ["cache-delete-source"],
                "country_filter": ["不存在的国家"],
            },
        },
        headers=auth_headers,
    )
    assert package_response.status_code == 201
    token = package_response.json()["token"]
    first = client.get(f"/sub/{token}")
    assert first.status_code == 200
    assert "cache-delete.example.com" in first.text

    deleted = client.delete(f"/api/sources/{source_id}", headers=auth_headers)
    assert deleted.status_code == 204

    after_delete = client.get(f"/sub/{token}")
    assert after_delete.status_code == 404
    assert after_delete.json()["detail"] == "套餐暂无可用节点"


def test_rename_source_invalidates_related_subscription_cache(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """来源重命名后，旧的订阅缓存必须立即失效。"""

    source_response = client.post(
        "/api/sources",
        json={"name": "cache-rename-source", "url": "https://example.com/cache-rename"},
        headers=auth_headers,
    )
    assert source_response.status_code == 201
    source_id = source_response.json()["id"]

    db = SessionLocal()
    try:
        node = Node(
            source_id=source_id,
            source_name="cache-rename-source",
            original_name="缓存重命名节点",
            name="缓存重命名节点",
            type="vless",
            server="cache-rename.example.com",
            port=443,
            uuid="cache-rename-uuid",
            country="不存在的国家",
            node_fingerprint=build_node_fingerprint(
                node_type="vless",
                server="cache-rename.example.com",
                port=443,
                uuid="cache-rename-uuid",
            ),
        )
        db.add(node)
        db.commit()
    finally:
        db.close()

    package_response = client.post(
        "/api/packages",
        json={
            "name": "cache-rename-package",
            "rules": {
                "source_filter": ["cache-rename-source"],
                "country_filter": ["不存在的国家"],
            },
        },
        headers=auth_headers,
    )
    assert package_response.status_code == 201
    token = package_response.json()["token"]
    first = client.get(f"/sub/{token}")
    assert first.status_code == 200

    db = SessionLocal()
    try:
        package = db.scalar(select(Package).where(Package.name == "cache-rename-package"))
        assert package is not None
        assert cache_service.get(SubscriptionService.cache_key(package)) is not None
    finally:
        db.close()

    renamed = client.put(
        f"/api/sources/{source_id}",
        json={"name": "cache-rename-source-new"},
        headers=auth_headers,
    )
    assert renamed.status_code == 200

    db = SessionLocal()
    try:
        package = db.scalar(select(Package).where(Package.name == "cache-rename-package"))
        assert package is not None
        assert cache_service.get(SubscriptionService.cache_key(package)) is None
    finally:
        db.close()


def test_delete_source_does_not_expand_package_to_other_sources(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """删除套餐筛选来源后，不能把筛选扩大为全部来源。"""

    first = client.post(
        "/api/sources",
        json={"name": "delete-filter-source-a", "url": "https://example.com/delete-a"},
        headers=auth_headers,
    )
    second = client.post(
        "/api/sources",
        json={"name": "delete-filter-source-b", "url": "https://example.com/delete-b"},
        headers=auth_headers,
    )
    assert first.status_code == 201 and second.status_code == 201

    db = SessionLocal()
    try:
        for source_id, source_name, server, suffix in (
            (first.json()["id"], "delete-filter-source-a", "delete-a.example.com", "a"),
            (second.json()["id"], "delete-filter-source-b", "delete-b.example.com", "b"),
        ):
            db.add(
                Node(
                    source_id=source_id,
                    source_name=source_name,
                    original_name=source_name,
                    name=source_name,
                    type="vless",
                    server=server,
                    port=443,
                    uuid=f"delete-filter-uuid-{suffix}",
                    node_fingerprint=build_node_fingerprint(
                        node_type="vless",
                        server=server,
                        port=443,
                        uuid=f"delete-filter-uuid-{suffix}",
                    ),
                )
            )
        db.commit()
    finally:
        db.close()

    package = client.post(
        "/api/packages",
        json={
            "name": "delete-filter-package",
            "rules": {"source_filter": ["delete-filter-source-a"]},
        },
        headers=auth_headers,
    )
    assert package.status_code == 201
    token = package.json()["token"]
    assert client.get(f"/sub/{token}").status_code == 200

    deleted = client.delete(f"/api/sources/{first.json()['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    response = client.get(f"/sub/{token}")
    assert response.status_code == 404
    assert response.json()["detail"] == "套餐暂无可用节点"


def test_create_source_invalid_url(client: TestClient, auth_headers: dict[str, str]) -> None:
    """非法 URL 应返回 400。"""

    response = client.post(
        "/api/sources",
        json={"name": "bad_url", "url": "not-a-url"},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.parametrize("url", ["http://127.0.0.1/feed", "http://localhost/feed", "http://10.0.0.1/feed"])
def test_create_source_rejects_internal_url(
    client: TestClient, auth_headers: dict[str, str], url: str
) -> None:
    """来源地址不能直接指向本机或内网地址。"""

    response = client.post(
        "/api/sources",
        json={"name": "内网来源", "url": url},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_update_source_rejects_explicit_null_required_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """来源名称和 URL 显式传 null 时应返回业务校验错误。"""

    created = client.post(
        "/api/sources",
        json={"name": "null-source", "url": "https://example.com/sub"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    response = client.put(
        f"/api/sources/{created.json()['id']}",
        json={"name": None},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "不能为 null" in response.json()["detail"]


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
