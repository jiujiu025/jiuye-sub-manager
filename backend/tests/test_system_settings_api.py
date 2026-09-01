"""系统设置接口测试。"""

from __future__ import annotations

import pytest
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


def test_settings_require_auth(client: TestClient) -> None:
    response = client.get("/api/system/settings")
    assert response.status_code == 401


def test_get_and_update_settings(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """系统设置应可读取并更新，修改后立即生效。"""

    response = client.get("/api/system/settings", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    for key in (
        "sync_interval_minutes",
        "sync_enabled",
        "cache_ttl_seconds",
        "dedup_source_priority",
    ):
        assert key in payload

    update_response = client.put(
        "/api/system/settings",
        json={
            "sync_interval_minutes": 7,
            "sync_enabled": False,
            "cache_ttl_seconds": 600,
            "dedup_source_priority": ["自有节点", "机场A"],
        },
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["sync_interval_minutes"] == 7
    assert updated["sync_enabled"] is False
    assert updated["cache_ttl_seconds"] == 600
    assert updated["dedup_source_priority"] == ["自有节点", "机场A"]

    # 恢复默认值，避免影响其他测试
    restore_response = client.put(
        "/api/system/settings",
        json={
            "sync_interval_minutes": 5,
            "sync_enabled": True,
            "cache_ttl_seconds": 300,
            "dedup_source_priority": [],
        },
        headers=auth_headers,
    )
    assert restore_response.status_code == 200
