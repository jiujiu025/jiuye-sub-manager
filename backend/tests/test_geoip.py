"""节点地区识别测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models.node import Node
from app.services.geoip_service import GeoIPService


class FakeResponse:
    """最小地理服务响应。"""

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeClient:
    """记录请求次数，避免测试依赖公网。"""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def get(self, url: str, **_: object) -> FakeResponse:
        self.urls.append(url)
        return FakeResponse(self.payload)


def _node(name: str, server: str, fingerprint: str) -> Node:
    return Node(
        source_name="导入外部节点",
        original_name=name,
        name=name,
        type="vless",
        server=server,
        port=443,
        uuid=fingerprint,
        node_fingerprint=fingerprint,
    )


def test_geoip_resolves_public_ip_and_reuses_cache(monkeypatch) -> None:
    """同一公网 IP 只请求一次，并把国家代码转换为中文。"""

    db = SessionLocal()
    client = FakeClient({"success": True, "country_code": "SG", "country": "Singapore"})
    try:
        first = _node("线路 A", "edge-a.example", "geo-test-1")
        second = _node("线路 B", "edge-b.example", "geo-test-2")
        db.add_all([first, second])
        db.commit()
        monkeypatch.setattr("app.services.geoip_service.resolve_public_ip", lambda _: "1.2.3.4")
        result = GeoIPService(db, http_client=client).resolve_nodes(limit=10)
        assert result["resolved"] == 2
        assert result["cached"] == 1
        assert client.urls == ["https://ipwho.is/1.2.3.4"]
        assert first.country == "新加坡"
        assert second.country == "新加坡"
    finally:
        db.close()


def test_geoip_prefers_name_and_skips_private_ip(monkeypatch) -> None:
    """名称已有明确地区时不调用外部服务，私网地址也不外发。"""

    db = SessionLocal()
    client = FakeClient({"success": True, "country_code": "US"})
    try:
        named = _node("香港-01", "10.0.0.8", "geo-test-3")
        private = _node("随机线路", "10.0.0.9", "geo-test-4")
        db.add_all([named, private])
        db.commit()
        monkeypatch.setattr("app.services.geoip_service.resolve_public_ip", lambda value: None)
        result = GeoIPService(db, http_client=client).resolve_nodes(limit=10)
        assert result["name_resolved"] == 1
        assert named.country == "香港"
        assert private.country is None
        assert client.urls == []
    finally:
        db.close()


def test_country_resolve_endpoint_returns_safe_statistics(
    client: TestClient, monkeypatch
) -> None:
    """管理员接口只返回统计信息，不回显服务器地址或敏感节点字段。"""

    login = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    monkeypatch.setattr(
        "app.api.nodes.GeoIPService.resolve_nodes",
        lambda self, **_: {
            "processed": 2,
            "resolved": 1,
            "name_resolved": 0,
            "cached": 1,
            "skipped": 0,
            "failed": 1,
            "remaining": False,
            "errors": ["地理服务请求失败"],
        },
    )
    response = client.post("/api/nodes/country/resolve", json={}, headers=headers)
    assert response.status_code == 200
    assert response.json()["resolved"] == 1
    assert "server" not in response.json()
