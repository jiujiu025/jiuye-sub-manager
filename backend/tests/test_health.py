"""健康检查接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    """健康检查应返回 ok。"""

    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
