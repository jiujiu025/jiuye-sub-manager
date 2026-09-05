"""健康检查接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_healthz(client: TestClient) -> None:
    """健康检查应返回 ok。"""

    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_healthz_returns_503_when_database_is_unavailable(
    client: TestClient, monkeypatch
) -> None:
    """数据库不可用时健康检查必须返回 503。"""

    def fail_execute(self: Session, statement):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(Session, "execute", fail_execute)
    response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json()["detail"] == "数据库不可用"
