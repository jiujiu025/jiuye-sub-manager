"""统一节点池 REST API 测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.node import Node
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


def test_nodes_require_auth(client: TestClient) -> None:
    """未登录访问节点池应返回 401。"""

    response = client.get("/api/nodes")
    assert response.status_code == 401


def test_list_nodes_with_filter(client: TestClient, auth_headers: dict[str, str]) -> None:
    """节点池列表应支持筛选并脱敏敏感字段。"""

    db = SessionLocal()
    try:
        nodes = [
            Node(
                source_id=None,
                source_name="自有节点",
                original_name="HK-VLESS",
                name="HK-VLESS",
                type="vless",
                server="hk.example.com",
                port=443,
                uuid="uuid-secret",
                country="香港",
                node_fingerprint=build_node_fingerprint(
                    node_type="vless", server="hk.example.com", port=443, uuid="uuid-secret"
                ),
            ),
            Node(
                source_id=None,
                source_name="自有节点",
                original_name="JP-SS",
                name="JP-SS",
                type="shadowsocks",
                server="jp.example.com",
                port=8388,
                password="password-secret",
                cipher="aes-256-gcm",
                country="日本",
                node_fingerprint=build_node_fingerprint(
                    node_type="shadowsocks",
                    server="jp.example.com",
                    port=8388,
                    password="password-secret",
                    cipher="aes-256-gcm",
                ),
            ),
        ]
        db.add_all(nodes)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/nodes?country=香港", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    item = payload["items"][0]
    assert item["country"] == "香港"
    assert item["uuid_masked"] is not None
    assert "uuid" not in item
    assert "password" not in item

    response = client.get("/api/nodes?node_type=shadowsocks", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_create_self_vless_node(client: TestClient, auth_headers: dict[str, str]) -> None:
    """自有 VLESS 节点应自动识别国家并写入节点池。"""

    response = client.post(
        "/api/nodes",
        json={
            "name": "HK-01",
            "type": "vless",
            "server": "my-hk.example.com",
            "port": 443,
            "uuid": "my-uuid",
            "network": "tcp",
            "security": "reality",
            "sni": "my-hk.example.com",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["source_name"] == "自有节点"
    assert payload["uuid"] == "my-uuid"
    assert payload["country"] == "香港"


def test_create_self_node_missing_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """VLESS 缺 UUID、SS 缺密码/加密方式都应返回 400。"""

    vless_response = client.post(
        "/api/nodes",
        json={
            "name": "bad-vless",
            "type": "vless",
            "server": "example.com",
            "port": 443,
        },
        headers=auth_headers,
    )
    assert vless_response.status_code == 400

    ss_response = client.post(
        "/api/nodes",
        json={
            "name": "bad-ss",
            "type": "shadowsocks",
            "server": "example.com",
            "port": 8388,
            "password": "pass",
        },
        headers=auth_headers,
    )
    assert ss_response.status_code == 400


def test_self_node_replaces_upstream(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """同指纹自有节点应替换低优先级上游节点。"""

    db = SessionLocal()
    try:
        upstream = Node(
            source_id=None,
            source_name="机场A",
            original_name="HK-UPSTREAM",
            name="HK-UPSTREAM",
            type="vless",
            server="dup.example.com",
            port=443,
            uuid="dup-uuid",
            country="香港",
            node_fingerprint=build_node_fingerprint(
                node_type="vless",
                server="dup.example.com",
                port=443,
                uuid="dup-uuid",
            ),
        )
        db.add(upstream)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/nodes",
        json={
            "name": "HK-SELF",
            "type": "vless",
            "server": "dup.example.com",
            "port": 443,
            "uuid": "dup-uuid",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["source_name"] == "自有节点"

    db = SessionLocal()
    try:
        rows = db.scalars(select(Node).where(Node.server == "dup.example.com")).all()
        assert len(rows) == 1
        assert rows[0].source_name == "自有节点"
    finally:
        db.close()


def test_batch_nodes_actions(client: TestClient, auth_headers: dict[str, str]) -> None:
    """批量启用/禁用/删除应生效。"""

    db = SessionLocal()
    try:
        nodes = []
        for index in range(2):
            node = Node(
                source_id=None,
                source_name="自有节点",
                original_name=f"batch-{index}",
                name=f"batch-{index}",
                type="vless",
                server=f"batch-{index}.example.com",
                port=443,
                uuid=f"batch-uuid-{index}",
                node_fingerprint=build_node_fingerprint(
                    node_type="vless",
                    server=f"batch-{index}.example.com",
                    port=443,
                    uuid=f"batch-uuid-{index}",
                ),
            )
            db.add(node)
            nodes.append(node)
        db.commit()
        node_ids = [node.id for node in nodes]
    finally:
        db.close()

    disable_response = client.post(
        "/api/nodes/batch",
        json={"ids": node_ids, "action": "disable"},
        headers=auth_headers,
    )
    assert disable_response.status_code == 200

    db = SessionLocal()
    try:
        disabled = db.scalars(
            select(Node).where(Node.id.in_(node_ids))
        ).all()
        assert all(node.enabled is False for node in disabled)
    finally:
        db.close()

    delete_response = client.post(
        "/api/nodes/batch",
        json={"ids": node_ids, "action": "delete"},
        headers=auth_headers,
    )
    assert delete_response.status_code == 200
    db = SessionLocal()
    try:
        remaining = db.scalars(
            select(Node).where(Node.id.in_(node_ids))
        ).all()
        assert remaining == []
    finally:
        db.close()
