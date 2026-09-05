"""MVP 最终验收端到端测试。"""

from __future__ import annotations

import base64
from urllib.parse import quote

import pytest
from curl_cffi.requests import errors as curl_errors
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.source import Source
from app.services.sync_service import SyncService
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


def _subscription(entries: list[tuple[str, str, str]]) -> str:
    """entries: (uuid, host, 中文名称)"""

    lines = [
        (
            f"vless://{uuid}@{host}:443"
            f"?security=reality&sni={host}#{quote(name)}"
        )
        for uuid, host, name in entries
    ]
    return base64.b64encode("\n".join(lines).encode("utf-8")).decode("ascii")


def _mock_sync(db, source: Source, payload: str) -> None:
    client = FakeClient(
        lambda url, kwargs: FakeResponse(200, payload)
    )
    result = SyncService(db, http_client=client).sync_source(source)
    assert result.status == "success"


def test_full_acceptance_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    """按验收流程完整跑通：双上游、双套餐、更新、故障保留、Token 重生成。"""

    db = SessionLocal()
    try:
        source_a = Source(
            name="e2e机场A",
            url="https://provider-a.example/sub",
            enabled=True,
            format="auto",
        )
        source_b = Source(
            name="e2e机场B",
            url="https://provider-b.example/sub",
            enabled=True,
            format="auto",
        )
        db.add_all([source_a, source_b])
        db.commit()
        db.refresh(source_a)
        db.refresh(source_b)

        # 两个上游首次同步
        _mock_sync(
            db,
            source_a,
            _subscription(
                [
                    ("uuid-hk-a", "hk-a.example.com", "香港01"),
                    ("uuid-jp-a", "jp-a.example.com", "日本01"),
                ]
            ),
        )
        _mock_sync(
            db,
            source_b,
            _subscription(
                [
                    ("uuid-us-b", "us-b.example.com", "美国01"),
                    ("uuid-sg-b", "sg-b.example.com", "新加坡01"),
                ]
            ),
        )
    finally:
        db.close()

    # 添加自有 VLESS 与 SS
    self_vless = client.post(
        "/api/nodes",
        json={
            "name": "自有香港",
            "type": "vless",
            "server": "self-hk.example.com",
            "port": 443,
            "uuid": "00000000-0000-0000-0000-000000000005",
        },
        headers=auth_headers,
    )
    assert self_vless.status_code == 201
    self_ss = client.post(
        "/api/nodes",
        json={
            "name": "自有新加坡",
            "type": "shadowsocks",
            "server": "self-sg.example.com",
            "port": 8388,
            "password": "self-sg-pass",
            "cipher": "aes-256-gcm",
        },
        headers=auth_headers,
    )
    assert self_ss.status_code == 201

    # 创建两个不同规则的套餐
    package_a = client.post(
        "/api/packages",
        json={
            "name": "e2e套餐A",
            "rules": {"source_filter": ["e2e机场A", "自有节点"]},
        },
        headers=auth_headers,
    )
    package_b = client.post(
        "/api/packages",
        json={
            "name": "e2e套餐B",
            "rules": {"source_filter": ["e2e机场B", "自有节点"]},
        },
        headers=auth_headers,
    )
    assert package_a.status_code == 201
    assert package_b.status_code == 201
    token_a = package_a.json()["token"]
    token_b = package_b.json()["token"]
    url_a = package_a.json()["subscription_url"]
    assert url_a.endswith(f"/sub/{token_a}")
    assert token_a != token_b

    # 两个订阅输出节点不同
    yaml_a = client.get(f"/sub/{token_a}").text
    yaml_b = client.get(f"/sub/{token_b}").text
    assert "hk-a.example.com" in yaml_a
    assert "us-b.example.com" not in yaml_a
    assert "us-b.example.com" in yaml_b
    assert "hk-a.example.com" not in yaml_b
    assert "self-hk.example.com" in yaml_a
    assert "self-sg.example.com" in yaml_b
    assert "proxy-providers" not in yaml_a
    assert "provider-a.example" not in yaml_a

    # 修改机场A内容并再次同步，原 URL 不变、节点自动更新
    db = SessionLocal()
    try:
        source_a = db.scalar(select(Source).where(Source.name == "e2e机场A"))
        assert source_a is not None
        _mock_sync(
            db,
            source_a,
            _subscription(
                [
                    ("uuid-kr-a", "kr-a.example.com", "韩国01"),
                    ("uuid-jp-a", "jp-a.example.com", "日本01"),
                ]
            ),
        )
    finally:
        db.close()

    yaml_a_updated = client.get(f"/sub/{token_a}").text
    assert "kr-a.example.com" in yaml_a_updated
    assert "hk-a.example.com" not in yaml_a_updated
    assert client.get(f"/sub/{token_b}").text.count("us-b.example.com") >= 1

    # 模拟上游超时：旧节点必须保留
    db = SessionLocal()
    try:
        source_b = db.scalar(select(Source).where(Source.name == "e2e机场B"))
        assert source_b is not None
        timeout_client = FakeClient(
            lambda url, kwargs: (_ for _ in ()).throw(
                curl_errors.RequestsError("Operation timed out")
            )
        )
        result = SyncService(db, http_client=timeout_client).sync_source(source_b)
        assert result.status == "failed"
        assert "超时" in result.error
    finally:
        db.close()
    assert "us-b.example.com" in client.get(f"/sub/{token_b}").text
    assert "sg-b.example.com" in client.get(f"/sub/{token_b}").text

    # 模拟空内容：不清空旧节点
    db = SessionLocal()
    try:
        source_b = db.scalar(select(Source).where(Source.name == "e2e机场B"))
        assert source_b is not None
        empty_client = FakeClient(
            lambda url, kwargs: FakeResponse(200, "")
        )
        result = SyncService(db, http_client=empty_client).sync_source(source_b)
        assert result.status == "failed"
        assert "空内容" in result.error
    finally:
        db.close()
    assert "us-b.example.com" in client.get(f"/sub/{token_b}").text

    # 重新生成套餐A Token：旧 Token 失效，新 Token 正常
    regenerate = client.post(
        f"/api/packages/{package_a.json()['id']}/regenerate-token",
        headers=auth_headers,
    )
    assert regenerate.status_code == 200
    new_token_a = regenerate.json()["token"]
    assert new_token_a != token_a
    assert client.get(f"/sub/{token_a}").status_code == 404
    new_yaml_a = client.get(f"/sub/{new_token_a}").text
    assert "kr-a.example.com" in new_yaml_a
