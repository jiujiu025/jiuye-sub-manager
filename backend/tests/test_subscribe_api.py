"""公开订阅接口与端到端验收测试。"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.core import config
from app.core.rate_limit import rate_limiter
from app.models.log import SubscriptionLog
from app.models.node import Node
from app.models.package import Package
from app.models.source import Source
from app.services.sync_service import SyncService
from app.services.subscription_service import SubscriptionService
from app.utils.fingerprint import build_node_fingerprint
from tests.fakes import FakeClient, FakeResponse


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _add_node(db, *, name: str, server: str, uuid: str, country: str) -> None:
    node = Node(
        source_id=None,
        source_name="自有节点",
        original_name=name,
        name=name,
        type="vless",
        server=server,
        port=443,
        uuid=uuid,
        country=country,
        node_fingerprint=build_node_fingerprint(
            node_type="vless", server=server, port=443, uuid=uuid
        ),
    )
    db.add(node)


def _subscription_for(client: TestClient, token: str) -> str:
    response = client.get(f"/sub/{token}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/yaml")
    return response.text


def test_invalid_token_returns_404(client: TestClient) -> None:
    """非法 Token 应返回 404。"""

    response = client.get("/sub/not-a-real-token")
    assert response.status_code == 404


def test_subscription_rate_limit_is_scoped_to_ip_and_token(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """订阅限流应限制同一 IP+Token，正常刷新不超过默认窗口。"""

    db = SessionLocal()
    try:
        _add_node(
            db,
            name="限流节点",
            server="rate-limit.example.com",
            uuid="rate-limit-uuid",
            country="香港",
        )
        db.commit()
        node_id = db.scalar(
            select(Node.id).where(Node.server == "rate-limit.example.com")
        )
    finally:
        db.close()

    created = client.post(
        "/api/packages",
        json={"name": "订阅限流套餐", "rules": {"node_ids": [node_id]}},
        headers=auth_headers,
    )
    token = created.json()["token"]
    settings = config.get_settings()
    monkeypatch.setattr(settings, "subscription_rate_limit", 2)
    monkeypatch.setattr(settings, "subscription_rate_window_seconds", 60)
    rate_limiter.clear_all()

    assert client.get(f"/sub/{token}").status_code == 200
    assert client.get(f"/sub/{token}").status_code == 200
    limited = client.get(f"/sub/{token}")
    assert limited.status_code == 429
    assert limited.json()["detail"] == "请求过于频繁，请稍后再试"
    assert limited.headers["retry-after"]


def test_subscription_cache_isolated_by_output_format(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """同一 Token 的不同导出格式必须使用不同缓存维度。"""

    db = SessionLocal()
    try:
        _add_node(
            db,
            name="缓存格式节点",
            server="cache-format.example.com",
            uuid="cache-format-uuid",
            country="香港",
        )
        db.commit()
        node_id = db.scalar(
            select(Node.id).where(Node.server == "cache-format.example.com")
        )
    finally:
        db.close()

    created = client.post(
        "/api/packages",
        json={"name": "格式隔离套餐", "rules": {"node_ids": [node_id]}},
        headers=auth_headers,
    )
    package_id = created.json()["id"]
    token = created.json()["token"]
    assert client.get(f"/sub/{token}?client=clash").status_code == 200
    assert client.get(f"/sub/{token}?client=uri").status_code == 200

    db = SessionLocal()
    try:
        package = db.get(Package, package_id)
        assert package is not None
        assert SubscriptionService.cache_key(package, "clash") != SubscriptionService.cache_key(
            package, "uri"
        )
        other_package = Package(
            id=package_id + 100000,
            token_hash="b" * 64,
            name="其他缓存套餐",
        )
        assert SubscriptionService.cache_key(package, "clash") != SubscriptionService.cache_key(
            other_package, "clash"
        )
    finally:
        db.close()


def test_disabled_package_returns_403(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """禁用套餐应返回 403。"""

    create_response = client.post(
        "/api/packages", json={"name": "禁用订阅套餐"}, headers=auth_headers
    )
    package_id = create_response.json()["id"]
    token = create_response.json()["token"]
    client.post(f"/api/packages/{package_id}/toggle", headers=auth_headers)

    response = client.get(f"/sub/{token}")
    assert response.status_code == 403


def test_empty_package_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """套餐无节点应返回明确错误而不是损坏配置。"""

    create_response = client.post(
        "/api/packages",
        json={"name": "空订阅套餐", "rules": {"source_filter": ["不存在的来源"]}},
        headers=auth_headers,
    )
    token = create_response.json()["token"]
    response = client.get(f"/sub/{token}")
    assert response.status_code == 404
    assert response.json()["detail"] == "套餐暂无可用节点"


def test_subscription_cache_hit_logs_cached_node_count(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """命中订阅缓存时，访问日志仍应记录实际节点数量。"""

    db = SessionLocal()
    try:
        _add_node(
            db,
            name="缓存节点",
            server="cache-node.example.com",
            uuid="cache-node-uuid",
            country="香港",
        )
        db.commit()
        node_id = db.scalar(
            select(Node.id).where(Node.server == "cache-node.example.com")
        )
    finally:
        db.close()

    created = client.post(
        "/api/packages",
        json={"name": "缓存计数套餐", "rules": {"node_ids": [node_id]}},
        headers=auth_headers,
    )
    assert created.status_code == 201
    package_id = created.json()["id"]
    token = created.json()["token"]
    assert client.get(f"/sub/{token}").status_code == 200
    assert client.get(f"/sub/{token}").status_code == 200

    db = SessionLocal()
    try:
        logs = list(
            db.scalars(
                select(SubscriptionLog)
                .where(SubscriptionLog.package_id == package_id)
                .order_by(SubscriptionLog.id.desc())
            ).all()
        )
        assert len(logs) >= 2
        assert logs[0].node_count == 1
        assert logs[1].node_count == 1
    finally:
        db.close()


def test_active_subscription_advertises_hourly_refresh(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """正常订阅应通过响应头建议客户端每小时重新拉取。"""

    db = SessionLocal()
    try:
        _add_node(
            db,
            name="刷新提示节点",
            server="refresh-interval.example.com",
            uuid="refresh-interval-uuid",
            country="香港",
        )
        db.commit()
        node_id = db.scalar(
            select(Node.id).where(Node.server == "refresh-interval.example.com")
        )
    finally:
        db.close()

    created = client.post(
        "/api/packages",
        json={"name": "每小时刷新套餐", "rules": {"node_ids": [node_id]}},
        headers=auth_headers,
    )
    response = client.get(f"/sub/{created.json()['token']}")
    assert response.status_code == 200
    assert response.headers["profile-update-interval"] == "3600"
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert "refresh-interval.example.com" in response.text


def test_subscription_headers_advertise_display_name_for_client_import(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """客户端扫码或导入时应能从响应头取得套餐显示名称。"""

    db = SessionLocal()
    try:
        _add_node(
            db,
            name="二维码备注节点",
            server="qr-name.example.com",
            uuid="qr-name-uuid",
            country="香港",
        )
        db.commit()
        node_id = db.scalar(select(Node.id).where(Node.server == "qr-name.example.com"))
    finally:
        db.close()

    created = client.post(
        "/api/packages",
        json={
            "name": "后台套餐名",
            "subscription_name": "手机主订阅",
            "rules": {"node_ids": [node_id]},
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    token = created.json()["token"]

    response = client.get(f"/sub/{token}?client=clash")
    assert response.status_code == 200
    assert response.headers["profile-title"] == "%E6%89%8B%E6%9C%BA%E4%B8%BB%E8%AE%A2%E9%98%85"
    disposition = response.headers["content-disposition"]
    assert "filename*=UTF-8''%E6%89%8B%E6%9C%BA%E4%B8%BB%E8%AE%A2%E9%98%85" in disposition
    assert 'filename="subscription.yaml"' in disposition
    assert "\n" not in disposition and '"手机主订阅"' not in disposition
    assert "qr-name.example.com" in response.text

    for client_format in ("mihomo", "singbox", "uri", "base64"):
        formatted = client.get(f"/sub/{token}?client={client_format}")
        assert formatted.status_code == 200
        assert formatted.headers["profile-title"] == "%E6%89%8B%E6%9C%BA%E4%B8%BB%E8%AE%A2%E9%98%85"


def test_expired_subscription_bypasses_cache_and_returns_notice_for_all_formats(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """到期后不能继续命中旧节点缓存，所有订阅格式只返回续费提示线路。"""

    db = SessionLocal()
    try:
        _add_node(
            db,
            name="到期前真实节点",
            server="expired-cache.example.com",
            uuid="expired-cache-uuid",
            country="香港",
        )
        db.commit()
        node_id = db.scalar(
            select(Node.id).where(Node.server == "expired-cache.example.com")
        )
    finally:
        db.close()

    created = client.post(
        "/api/packages",
        json={
            "name": "缓存到期套餐",
            "rules": {"node_ids": [node_id]},
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    package_id = created.json()["id"]
    token = created.json()["token"]

    first = client.get(f"/sub/{token}")
    assert first.status_code == 200
    assert "expired-cache.example.com" in first.text

    expired = client.put(
        f"/api/packages/{package_id}",
        json={"expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()},
        headers=auth_headers,
    )
    assert expired.status_code == 200

    for client_format, content_type in (
        ("clash", "application/yaml"),
        ("mihomo", "application/yaml"),
        ("singbox", "application/json"),
        ("uri", "text/plain"),
    ):
        response = client.get(f"/sub/{token}?client={client_format}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(content_type)
        assert response.headers["x-subscription-expired"] == "true"
        assert response.headers["profile-update-interval"] == "3600"
        assert "expired-cache.example.com" not in response.text
        assert "订阅已到期，请续费使用" in unquote(response.text)

def test_subscription_end_to_end(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """上游修改后再次同步，原订阅 URL 应自动返回新节点。"""

    db = SessionLocal()
    try:
        source = Source(
            name="集成机场",
            url="https://provider.example.com/sub",
            enabled=True,
            allow_empty_override=False,
            format="auto",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        hk_payload = base64.b64encode(
            (
                "vless://uuid-hk@hk-a.example.com:443"
                "?security=reality&sni=hk-a.example.com#%E9%A6%99%E6%B8%AF01"
            ).encode("utf-8")
        ).decode("ascii")
        jp_payload = base64.b64encode(
            (
                "vless://uuid-jp@jp-b.example.com:443"
                "?security=reality&sni=jp-b.example.com#%E6%97%A5%E6%9C%AC01"
            ).encode("utf-8")
        ).decode("ascii")

        SyncService(
            db,
            http_client=FakeClient(
                lambda url, kwargs: FakeResponse(200, hk_payload)
            ),
        ).sync_source(source)
    finally:
        db.close()

    create_response = client.post(
        "/api/packages",
        json={
            "name": "自动更新套餐",
            "rules": {"country_filter": ["香港", "日本"]},
        },
        headers=auth_headers,
    )
    token = create_response.json()["token"]
    subscription_url = create_response.json()["subscription_url"]
    assert subscription_url.endswith(f"/sub/{token}")

    first_response = client.get(f"/sub/{token}")
    assert first_response.status_code == 200
    content_disposition = first_response.headers.get("content-disposition", "")
    assert "sub.yaml" not in content_disposition
    star_value = content_disposition.split("filename*=UTF-8''", 1)[1]
    assert unquote(star_value) == "自动更新套餐"
    first_yaml = first_response.text
    assert "hk-a.example.com" in first_yaml
    assert "proxy-providers" not in first_yaml
    assert "provider.example.com" not in first_yaml

    # 修改上游内容并再次同步，原 Token/URL 不变
    db = SessionLocal()
    try:
        source = db.scalar(select(Source).where(Source.name == "集成机场"))
        assert source is not None
        SyncService(
            db,
            http_client=FakeClient(
                lambda url, kwargs: FakeResponse(200, jp_payload)
            ),
        ).sync_source(source)
    finally:
        db.close()

    second_yaml = _subscription_for(client, token)
    assert "jp-b.example.com" in second_yaml
    assert "hk-a.example.com" not in second_yaml
    assert "provider.example.com" not in second_yaml


def test_regenerated_token_invalidates_old(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """重生成 Token 后旧 Token 立即失效，新 Token 可用。"""

    db = SessionLocal()
    try:
        _add_node(
            db,
            name="HK-01",
            server="regenerate.example.com",
            uuid="uuid-regenerate",
            country="香港",
        )
        db.commit()
    finally:
        db.close()

    create_response = client.post(
        "/api/packages",
        json={"name": "重生成订阅套餐"},
        headers=auth_headers,
    )
    package_id = create_response.json()["id"]
    old_token = create_response.json()["token"]

    regenerate_response = client.post(
        f"/api/packages/{package_id}/regenerate-token", headers=auth_headers
    )
    new_token = regenerate_response.json()["token"]
    assert new_token != old_token

    old_response = client.get(f"/sub/{old_token}")
    assert old_response.status_code == 404
    new_yaml = _subscription_for(client, new_token)
    assert "regenerate.example.com" in new_yaml


def test_revoked_token_is_uniformly_invalid_until_regenerated(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """吊销后旧 Token 立即失效，重新生成后新 Token 恢复访问。"""

    db = SessionLocal()
    try:
        _add_node(
            db,
            name="吊销节点",
            server="revoke.example.com",
            uuid="revoke-uuid",
            country="香港",
        )
        db.commit()
    finally:
        db.close()

    created = client.post(
        "/api/packages", json={"name": "吊销套餐"}, headers=auth_headers
    )
    package_id = created.json()["id"]
    old_token = created.json()["token"]
    assert client.get(f"/sub/{old_token}").status_code == 200

    revoked = client.post(
        f"/api/packages/{package_id}/revoke-token", headers=auth_headers
    )
    assert revoked.status_code == 200
    assert revoked.json()["subscription_url"] is None
    assert client.get(f"/sub/{old_token}").status_code == 404

    regenerated = client.post(
        f"/api/packages/{package_id}/regenerate-token", headers=auth_headers
    )
    new_token = regenerated.json()["token"]
    assert new_token != old_token
    assert client.get(f"/sub/{new_token}").status_code == 200
