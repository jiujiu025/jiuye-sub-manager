"""日志查询接口测试。"""

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


def test_logs_require_auth(client: TestClient) -> None:
    response = client.get("/api/logs?kind=sync")
    assert response.status_code == 401


def test_sync_logs(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/logs?kind=sync", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload


def test_subscription_logs(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/logs?kind=subscription", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()


def test_admin_logs(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/logs?kind=admin", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()


def test_system_logs(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/logs?kind=system", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json()["items"], list)


def test_error_logs(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/logs?kind=error", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json()["items"], list)
