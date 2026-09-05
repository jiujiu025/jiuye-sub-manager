"""后台概览接口测试。"""

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


def test_dashboard_requires_auth(client: TestClient) -> None:
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 401


def test_dashboard_stats(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    for key in (
        "source_count",
        "enabled_source_count",
        "node_count",
        "self_node_count",
        "package_count",
        "enabled_package_count",
        "failed_source_count",
        "last_sync_at",
    ):
        assert key in payload
