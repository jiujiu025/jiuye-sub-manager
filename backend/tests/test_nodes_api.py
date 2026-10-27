"""统一节点池 REST API 测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.node import Node
from app.models.source import Source
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
                uuid="00000000-0000-0000-0000-000000000001",
                country="香港",
                node_fingerprint=build_node_fingerprint(
                    node_type="vless", server="hk.example.com", port=443,
                    uuid="00000000-0000-0000-0000-000000000001",
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


def test_list_nodes_filters_health_status(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """资源池应在数据库分页前按健康状态筛选，异常线路包含异常和离线。"""

    statuses = ["healthy", "degraded", "offline", "unknown"]
    db = SessionLocal()
    try:
        nodes = []
        for index, health_status in enumerate(statuses, start=1):
            server = f"health-filter-{index}.example.com"
            uuid = f"00000000-0000-4000-8000-0000000002{index:02d}"
            nodes.append(
                Node(
                    source_id=None,
                    source_name="健康筛选来源",
                    original_name=f"健康筛选-{health_status}",
                    name=f"健康筛选-{health_status}",
                    type="vless",
                    server=server,
                    port=443,
                    uuid=uuid,
                    health_status=health_status,
                    node_fingerprint=build_node_fingerprint(
                        node_type="vless",
                        server=server,
                        port=443,
                        uuid=uuid,
                    ),
                )
            )
        db.add_all(nodes)
        db.commit()
    finally:
        db.close()

    for health_status in statuses:
        response = client.get(
            "/api/nodes",
            params={"health_status": health_status},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert all(
            item["health_status"] == health_status
            for item in response.json()["items"]
            if item["name"].startswith("健康筛选-")
        )

    attention = client.get(
        "/api/nodes",
        params={"health_status": "attention", "page_size": 100},
        headers=auth_headers,
    )
    assert attention.status_code == 200
    attention_items = [
        item
        for item in attention.json()["items"]
        if item["name"].startswith("健康筛选-")
    ]
    assert {item["health_status"] for item in attention_items} == {"degraded", "offline"}

    paged = client.get(
        "/api/nodes",
        params={"health_status": "attention", "page": 2, "page_size": 1},
        headers=auth_headers,
    )
    assert paged.status_code == 200
    assert paged.json()["total"] >= 2

    unauthenticated = client.get("/api/nodes?health_status=attention")
    assert unauthenticated.status_code == 401


def test_list_nodes_separates_subscription_and_custom_nodes(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """节点分类按来源 ID 判断，分页筛选不能把两类节点混在一起。"""

    source = client.post(
        "/api/sources",
        json={"name": "分类测试来源", "url": "https://example.com/subscription"},
        headers=auth_headers,
    )
    assert source.status_code == 201
    source_id = source.json()["id"]
    db = SessionLocal()
    try:
        db.add(
            Node(
                source_id=source_id,
                source_name="分类测试来源",
                source_type="upstream",
                original_name="上游分类节点",
                name="上游分类节点",
                type="vless",
                server="upstream.example.com",
                port=443,
                uuid="00000000-0000-4000-0000-000000000011",
                node_fingerprint=build_node_fingerprint(
                    node_type="vless",
                    server="upstream.example.com",
                    port=443,
                    uuid="00000000-0000-4000-0000-000000000011",
                ),
            )
        )
        db.commit()
    finally:
        db.close()

    subscription_nodes = client.get(
        "/api/nodes?source_kind=subscription", headers=auth_headers
    )
    custom_nodes = client.get("/api/nodes?source_kind=custom", headers=auth_headers)
    assert subscription_nodes.status_code == 200
    assert custom_nodes.status_code == 200
    assert any(item["source_id"] == source_id for item in subscription_nodes.json()["items"])
    assert all(item["source_id"] is None for item in custom_nodes.json()["items"])

    db = SessionLocal()
    try:
        # 历史手工节点可能没有 source_type，仍应归入外部节点分类。
        db.add(
            Node(
                source_name="导入外部节点",
                source_type=None,
                node_category="external",
                original_name="历史外部节点",
                name="历史外部节点",
                type="vless",
                server="legacy-external.example.com",
                port=443,
                uuid="00000000-0000-4000-0000-000000000012",
                node_fingerprint=build_node_fingerprint(
                    node_type="vless",
                    server="legacy-external.example.com",
                    port=443,
                    uuid="00000000-0000-4000-0000-000000000012",
                ),
            )
        )
        db.commit()
    finally:
        db.close()

    custom_nodes = client.get("/api/nodes?source_kind=custom", headers=auth_headers)
    assert any(item["name"] == "历史外部节点" for item in custom_nodes.json()["items"])


def test_create_self_vless_node(client: TestClient, auth_headers: dict[str, str]) -> None:
    """自有 VLESS 节点应自动识别国家并写入节点池。"""

    response = client.post(
        "/api/nodes",
        json={
            "name": "HK-01",
            "type": "vless",
            "server": "my-hk.example.com",
            "port": 443,
            "uuid": "00000000-0000-0000-0000-000000000002",
            "network": "tcp",
            "security": "reality",
            "sni": "my-hk.example.com",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["source_name"] == "自有节点"
    assert payload["uuid"] == "00000000-0000-0000-0000-000000000002"
    assert payload["country"] == "香港"


def test_anytls_import_and_single_node_export(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """AnyTLS 导入后应能通过节点分享接口导出 URI。"""

    imported = client.post(
        "/api/nodes/import",
        json={
            "content": "anytls://anytls-password@anytls.example.com:443"
            "?security=tls&sni=anytls.example.com#AnyTLS-01",
            "source_subtype": "custom_url",
            "format": "auto",
        },
        headers=auth_headers,
    )
    assert imported.status_code == 200
    assert imported.json()["success"] == 1

    db = SessionLocal()
    try:
        node = db.scalar(select(Node).where(Node.type == "anytls"))
        assert node is not None
        node_id = node.id
    finally:
        db.close()

    exported = client.get(f"/api/nodes/{node_id}/export", headers=auth_headers)
    assert exported.status_code == 200
    assert exported.json()["type"] == "anytls"
    assert exported.json()["content"].startswith("anytls://")


def test_legacy_socks5_node_can_be_shared(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """历史记录保存为 socks5 类型时，单节点分享仍应正常工作。"""

    db = SessionLocal()
    try:
        node = Node(
            source_id=None,
            source_name="导入外部节点",
            original_name="149.52.61.103",
            name="149.52.61.103",
            type="socks5",
            server="149.52.61.103",
            port=5001,
            username="legacy-user",
            password="legacy-pass",
            node_fingerprint=build_node_fingerprint(
                node_type="socks5",
                server="149.52.61.103",
                port=5001,
                username="legacy-user",
                password="legacy-pass",
            ),
        )
        db.add(node)
        db.commit()
        node_id = node.id
    finally:
        db.close()

    exported = client.get(f"/api/nodes/{node_id}/export", headers=auth_headers)

    assert exported.status_code == 200
    assert exported.json()["content"].startswith(
        "socks://legacy-user:legacy-pass@149.52.61.103:5001"
    )


def test_node_health_returns_unknown_without_active_probe(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """健康接口只提供稳定状态契约，不主动探测节点。"""

    created = client.post(
        "/api/nodes",
        json={
            "name": "健康检查节点",
            "type": "vless",
            "server": "health.example.com",
            "port": 443,
            "uuid": "00000000-0000-0000-0000-000000000003",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    node_id = created.json()["id"]

    health = client.get(f"/api/nodes/{node_id}/health", headers=auth_headers)
    assert health.status_code == 200
    assert health.json()["status"] == "unknown"
    assert health.json()["udp_status"] == "unknown"
    assert health.json()["udp_latency_ms"] is None
    assert client.get("/api/nodes/999999/health", headers=auth_headers).status_code == 404


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


def test_node_code_is_monotonic_and_note_is_searchable(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """节点编号删除后不复用，备注可以通过节点关键词检索。"""

    first = client.post(
        "/api/nodes",
        json={
            "name": "编号节点一",
            "type": "vless",
            "server": "code-one.example.com",
            "port": 443,
            "uuid": "00000000-0000-4000-8000-000000000101",
            "note": "主线路备注",
        },
        headers=auth_headers,
    )
    assert first.status_code == 201
    first_payload = first.json()
    assert first_payload["node_code"].startswith("N-")
    assert first_payload["note"] == "主线路备注"

    found = client.get(
        "/api/nodes", params={"keyword": "主线路备注"}, headers=auth_headers
    )
    assert found.status_code == 200
    assert any(item["id"] == first_payload["id"] for item in found.json()["items"])

    deleted = client.delete(f"/api/nodes/{first_payload['id']}", headers=auth_headers)
    assert deleted.status_code == 204

    second = client.post(
        "/api/nodes",
        json={
            "name": "编号节点二",
            "type": "vless",
            "server": "code-two.example.com",
            "port": 443,
            "uuid": "00000000-0000-4000-8000-000000000102",
        },
        headers=auth_headers,
    )
    assert second.status_code == 201
    assert second.json()["node_code"] != first_payload["node_code"]
    assert int(second.json()["node_code"].split("-")[-1]) > int(
        first_payload["node_code"].split("-")[-1]
    )


def test_node_usage_reports_packages_and_customer_subscriptions(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """节点使用关系应同时返回直接选中的套餐和客户订阅。"""

    node = client.post(
        "/api/nodes",
        json={
            "name": "使用关系节点",
            "type": "vless",
            "server": "usage.example.com",
            "port": 443,
            "uuid": "00000000-0000-4000-8000-000000000103",
        },
        headers=auth_headers,
    )
    assert node.status_code == 201
    node_id = node.json()["id"]
    package = client.post(
        "/api/packages",
        json={"name": "节点使用关系套餐", "rules": {"node_ids": [node_id]}},
        headers=auth_headers,
    )
    assert package.status_code == 201
    customer = client.post(
        "/api/customers",
        json={"name": "节点使用关系客户"},
        headers=auth_headers,
    )
    assert customer.status_code == 201
    subscription = client.post(
        "/api/subscriptions",
        json={"package_id": package.json()["id"], "customer_id": customer.json()["id"]},
        headers=auth_headers,
    )
    assert subscription.status_code == 201

    usage = client.get(f"/api/nodes/{node_id}/usage", headers=auth_headers)
    assert usage.status_code == 200
    payload = usage.json()
    target_package = next(
        item for item in payload["packages"] if item["package_id"] == package.json()["id"]
    )
    assert "直接选中" in target_package["match_types"]
    assert payload["customer_subscription_count"] >= 1
    assert any(
        item["customer_name"] == "节点使用关系客户"
        and item["package_id"] == package.json()["id"]
        for item in payload["customer_subscriptions"]
    )


def test_node_usage_reports_inherited_customer_manager(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """订阅未单独指定经理时，节点使用关系应显示客户默认经理。"""

    manager = client.post(
        "/api/users",
        json={
            "username": "usage-manager",
            "password": "ManagerPass123!",
            "role": "manager",
        },
        headers=auth_headers,
    )
    assert manager.status_code == 201
    node = client.post(
        "/api/nodes",
        json={
            "name": "继承经理节点",
            "type": "vless",
            "server": "inherited-manager.example.com",
            "port": 443,
            "uuid": "00000000-0000-4000-8000-000000000104",
        },
        headers=auth_headers,
    )
    assert node.status_code == 201
    package = client.post(
        "/api/packages",
        json={
            "name": "继承经理套餐",
            "rules": {"node_ids": [node.json()["id"]]},
        },
        headers=auth_headers,
    )
    assert package.status_code == 201
    customer = client.post(
        "/api/customers",
        json={"name": "继承经理客户", "manager_user_id": manager.json()["id"]},
        headers=auth_headers,
    )
    assert customer.status_code == 201
    subscription = client.post(
        "/api/subscriptions",
        json={
            "package_id": package.json()["id"],
            "customer_id": customer.json()["id"],
        },
        headers=auth_headers,
    )
    assert subscription.status_code == 201

    usage = client.get(
        f"/api/nodes/{node.json()['id']}/usage", headers=auth_headers
    )
    assert usage.status_code == 200
    inherited = next(
        item
        for item in usage.json()["customer_subscriptions"]
        if item["subscription_id"] == subscription.json()["id"]
    )
    assert inherited["manager_username"] == "usage-manager"


@pytest.mark.parametrize("uuid", ["not-a-uuid", "1234"])
def test_create_self_vless_rejects_invalid_uuid(
    client: TestClient, auth_headers: dict[str, str], uuid: str
) -> None:
    """创建 VLESS 节点时必须拒绝非法 UUID。"""

    response = client.post(
        "/api/nodes",
        json={
            "name": "invalid-vless-uuid",
            "type": "vless",
            "server": "example.com",
            "port": 443,
            "uuid": uuid,
        },
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "UUID" in response.json()["detail"]


def test_create_self_shadowsocks_rejects_invalid_cipher(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """创建 Shadowsocks 节点时必须拒绝项目白名单之外的 cipher。"""

    response = client.post(
        "/api/nodes",
        json={
            "name": "invalid-ss-cipher",
            "type": "shadowsocks",
            "server": "example.com",
            "port": 8388,
            "password": "password",
            "cipher": "unsupported-cipher",
        },
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "不支持的加密方式" in response.json()["detail"]


def test_import_invalid_uri_is_reported_without_blocking_valid_nodes(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """非法端口应成为失败项，不能阻断同批合法节点。"""

    response = client.post(
        "/api/nodes/import",
        json={
            "format": "uri",
            "content": (
                "vless://uuid-valid@hk-import.example.com:443#HK-valid\n"
                "vless://uuid-invalid@bad.example.com:bad#bad"
            ),
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["success"] == 1
    assert payload["failed"] == 1
    assert payload["failures"][0]["index"] == 2
    assert "端口" in payload["failures"][0]["reason"]


def test_update_self_node_revalidates_protocol_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """节点编辑不能清空 VLESS UUID 或 Shadowsocks 关键字段。"""

    vless = client.post(
        "/api/nodes",
        json={
            "name": "edit-vless",
            "type": "vless",
            "server": "edit-vless.example.com",
            "port": 443,
            "uuid": "00000000-0000-0000-0000-000000000003",
        },
        headers=auth_headers,
    )
    assert vless.status_code == 201
    invalid_vless = client.put(
        f"/api/nodes/{vless.json()['id']}",
        json={"uuid": ""},
        headers=auth_headers,
    )
    assert invalid_vless.status_code == 400
    assert "UUID" in invalid_vless.json()["detail"]

    invalid_vless_format = client.put(
        f"/api/nodes/{vless.json()['id']}",
        json={"uuid": "invalid-vless-uuid"},
        headers=auth_headers,
    )
    assert invalid_vless_format.status_code == 400
    assert "UUID" in invalid_vless_format.json()["detail"]

    invalid_enabled = client.put(
        f"/api/nodes/{vless.json()['id']}",
        json={"enabled": None},
        headers=auth_headers,
    )
    assert invalid_enabled.status_code == 400
    assert "enabled" in invalid_enabled.json()["detail"]

    shadowsocks = client.post(
        "/api/nodes",
        json={
            "name": "edit-ss",
            "type": "shadowsocks",
            "server": "edit-ss.example.com",
            "port": 8388,
            "password": "ss-password",
            "cipher": "aes-256-gcm",
        },
        headers=auth_headers,
    )
    assert shadowsocks.status_code == 201
    invalid_ss = client.put(
        f"/api/nodes/{shadowsocks.json()['id']}",
        json={"cipher": ""},
        headers=auth_headers,
    )
    assert invalid_ss.status_code == 400
    assert "加密方式" in invalid_ss.json()["detail"]

    invalid_ss_cipher = client.put(
        f"/api/nodes/{shadowsocks.json()['id']}",
        json={"cipher": "unsupported-cipher"},
        headers=auth_headers,
    )
    assert invalid_ss_cipher.status_code == 400
    assert "不支持的加密方式" in invalid_ss_cipher.json()["detail"]

    valid_update = client.put(
        f"/api/nodes/{shadowsocks.json()['id']}",
        json={"cipher": "CHACHA20-IETF-POLY1305", "password": "new-password"},
        headers=auth_headers,
    )
    assert valid_update.status_code == 200
    assert valid_update.json()["cipher"] == "CHACHA20-IETF-POLY1305"


def test_update_self_node_rejects_explicit_null_required_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """节点必填字段显式传 null 时应返回业务校验错误。"""

    created = client.post(
        "/api/nodes",
        json={
            "name": "null-field-node",
            "type": "vless",
            "server": "null-field.example.com",
            "port": 443,
            "uuid": "00000000-0000-0000-0000-000000000010",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    response = client.put(
        f"/api/nodes/{created.json()['id']}",
        json={"name": None},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "不能为 null" in response.json()["detail"]


def test_upstream_node_cannot_be_edited_into_self_node(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """上游节点只能修改启用状态，不能破坏来源归属。"""

    db = SessionLocal()
    try:
        source = Source(
            name="protected-source",
            url="https://example.com/protected",
            enabled=True,
        )
        db.add(source)
        db.flush()
        node = Node(
            source_id=source.id,
            source_name=source.name,
            original_name="upstream-node",
            name="upstream-node",
            type="vless",
            server="upstream.example.com",
            port=443,
            uuid="00000000-0000-0000-0000-000000000099",
            source_type="upstream",
            node_fingerprint=build_node_fingerprint(
                node_type="vless",
                server="upstream.example.com",
                port=443,
                uuid="00000000-0000-0000-0000-000000000099",
            ),
        )
        db.add(node)
        db.commit()
        node_id = node.id
    finally:
        db.close()

    edit = client.put(
        f"/api/nodes/{node_id}",
        json={"name": "should-not-change"},
        headers=auth_headers,
    )
    assert edit.status_code == 400
    assert "上游节点" in edit.json()["detail"]

    disable = client.put(
        f"/api/nodes/{node_id}",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert disable.status_code == 200
    assert disable.json()["enabled"] is False

    db = SessionLocal()
    try:
        stored = db.get(Node, node_id)
        assert stored is not None
        assert stored.source_id is not None
        assert stored.source_type == "upstream"
        assert stored.name == "upstream-node"
    finally:
        db.close()


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
            server="dup-self-only.example.com",
            port=443,
            uuid="00000000-0000-0000-0000-000000000004",
            country="香港",
            node_fingerprint=build_node_fingerprint(
                node_type="vless",
                server="dup-self-only.example.com",
                port=443,
                uuid="00000000-0000-0000-0000-000000000004",
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
            "server": "dup-self-only.example.com",
            "port": 443,
            "uuid": "00000000-0000-0000-0000-000000000004",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["source_name"] == "自有节点"

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(Node).where(Node.server == "dup-self-only.example.com")
        ).all()
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
