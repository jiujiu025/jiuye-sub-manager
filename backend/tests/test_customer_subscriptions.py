"""客户档案与独立客户订阅闭环测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_package(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post(
        "/api/packages",
        json={"name": name, "rules": {"node_ids": []}},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_customer(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post(
        "/api/customers",
        json={"name": name, "region": "香港", "contact": "example-contact"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_node(client: TestClient, headers: dict[str, str], variant: int = 0) -> None:
    response = client.post(
        "/api/nodes",
        json={
            "name": "客户订阅测试节点",
            "type": "vless",
            "server": f"198.51.100.{10 + variant}",
            "port": 443 + variant,
            "uuid": f"00000000-0000-4000-8000-00000000000{variant + 1}",
            "network": "tcp",
            "security": "tls",
            "tls": True,
            "source_subtype": "custom_manual",
        },
        headers=headers,
    )
    assert response.status_code == 201


def test_customer_crud_and_admin_only(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/customers",
        json={"name": "客户甲", "region": "日本", "contact": "contact-a", "note": "首购"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    customer_id = created.json()["id"]
    assert created.json()["subscription_count"] == 0

    updated = client.put(
        f"/api/customers/{customer_id}",
        json={"contact": "contact-b", "is_active": True},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["contact"] == "contact-b"
    assert client.get("/api/customers").status_code == 401


def test_customer_subscription_has_independent_token_lifecycle(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created_node = client.post(
        "/api/nodes",
        json={
            "name": "客户分享专用节点",
            "type": "vless",
            "server": "203.0.113.210",
            "port": 544,
            "uuid": "00000000-0000-4000-8000-000000000099",
            "network": "tcp",
            "security": "tls",
            "tls": True,
            "source_subtype": "custom_manual",
        },
        headers=auth_headers,
    )
    assert created_node.status_code == 201
    package_id = _create_package(client, auth_headers, "客户开通套餐")
    customer_id = _create_customer(client, auth_headers, "客户乙")
    created = client.post(
        "/api/subscriptions",
        json={
            "package_id": package_id,
            "customer_id": customer_id,
            "sale_price": "99.00",
            "cost_price": "20.00",
            "note": "管理员直开",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    payload = created.json()
    subscription_id = payload["id"]
    old_token = payload["token"]
    assert payload["customer_name"] == "客户乙"
    assert payload["package_name"] == "客户开通套餐"
    assert payload["sale_price"] == "99.00"
    assert payload["subscription_url"].endswith(f"/sub/{old_token}")

    listed = client.get("/api/subscriptions", headers=auth_headers)
    assert listed.status_code == 200
    item = next(row for row in listed.json() if row["id"] == subscription_id)
    assert item["token_prefix"] == old_token[:8]
    assert old_token not in listed.text

    new_response = client.post(
        f"/api/subscriptions/{subscription_id}/regenerate-token", headers=auth_headers
    )
    assert new_response.status_code == 200
    new_token = new_response.json()["token"]
    assert new_token != old_token
    assert client.get(f"/sub/{old_token}").status_code == 404
    assert client.get(f"/sub/{new_token}").status_code == 200

    revoked = client.post(
        f"/api/subscriptions/{subscription_id}/revoke-token", headers=auth_headers
    )
    assert revoked.status_code == 200
    assert revoked.json()["token_revoked_at"] is not None
    assert client.get(f"/sub/{new_token}").status_code == 404
    assert client.get(
        f"/api/subscriptions/{subscription_id}/subscription-url", headers=auth_headers
    ).status_code == 404


def test_company_cost_is_admin_only_and_sales_cost_is_manager_visible(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """公司成本价只对管理员可见，经理只能使用销售成本价。"""

    manager_id = _create_manager(client, auth_headers, "cost-manager")
    customer = client.post(
        "/api/customers",
        json={"name": "成本隔离客户", "manager_user_id": manager_id},
        headers=auth_headers,
    ).json()["id"]
    package_id = _create_package(client, auth_headers, "成本隔离套餐")
    created = client.post(
        "/api/subscriptions",
        json={
            "customer_id": customer,
            "package_id": package_id,
            "company_cost_price": "30.00",
            "sales_cost_price": "45.00",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    assert created.json()["company_cost_price"] == "30.00"
    assert created.json()["sales_cost_price"] == "45.00"

    manager_headers = _login_headers(client, "cost-manager", "ManagerPass123!")
    listed = client.get("/api/subscriptions", headers=manager_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["company_cost_price"] is None
    assert listed.json()[0]["sales_cost_price"] == "45.00"

    changed = client.put(
        f"/api/subscriptions/{created.json()['id']}",
        json={"company_cost_price": "999.00", "sales_cost_price": "50.00"},
        headers=manager_headers,
    )
    assert changed.status_code == 200
    assert changed.json()["company_cost_price"] is None
    assert changed.json()["sales_cost_price"] == "50.00"

    admin_view = client.get(
        f"/api/subscriptions/{created.json()['id']}", headers=auth_headers
    )
    assert admin_view.status_code == 200
    assert admin_view.json()["company_cost_price"] == "30.00"
    assert admin_view.json()["sales_cost_price"] == "50.00"


def test_expired_active_subscription_is_not_counted_as_active(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """数据库状态尚未更新时，已过期订阅也不能计入有效数量。"""

    manager_id = _create_manager(client, auth_headers, "expired-stats-manager")
    customer = client.post(
        "/api/customers",
        json={"name": "过期统计客户", "manager_user_id": manager_id},
        headers=auth_headers,
    ).json()["id"]
    package_id = _create_package(client, auth_headers, "过期统计套餐")
    created = client.post(
        "/api/subscriptions",
        json={
            "customer_id": customer,
            "package_id": package_id,
            "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
        headers=auth_headers,
    )
    assert created.status_code == 201

    manager_headers = _login_headers(
        client, "expired-stats-manager", "ManagerPass123!"
    )
    stats = client.get("/api/manager/stats", headers=manager_headers)
    assert stats.status_code == 200
    assert stats.json()["active_subscription_count"] == 0

    package = client.get("/api/packages", headers=manager_headers)
    assert package.status_code == 200
    usage = next(item for item in package.json() if item["id"] == package_id)[
        "used_by_customers"
    ]
    assert usage[0]["active_subscription_count"] == 0


def test_customer_subscription_expiry_does_not_change_package_expiry(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    _create_node(client, auth_headers)
    package_id = _create_package(client, auth_headers, "独立到期套餐")
    customer_id = _create_customer(client, auth_headers, "客户丙")
    package_token = client.get(
        f"/api/packages/{package_id}/subscription-url", headers=auth_headers
    ).json()["subscription_url"].rsplit("/", 1)[-1]
    created = client.post(
        "/api/subscriptions",
        json={
            "package_id": package_id,
            "customer_id": customer_id,
            "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    customer_token = created.json()["token"]
    expired = client.get(f"/sub/{customer_token}")
    assert expired.status_code == 200
    assert expired.headers.get("x-subscription-expired") == "true"
    package_response = client.get(f"/sub/{package_token}")
    assert package_response.status_code == 200
    assert package_response.headers.get("x-subscription-expired") != "true"


def test_customer_subscription_lines_expire_independently(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """同一客户订阅中，单条线路到期不应影响其他线路。"""

    for index, name in enumerate(("线路一", "线路二")):
        response = client.post(
            "/api/nodes",
            json={
                "name": name,
                "type": "vless",
                "server": f"198.51.100.{40 + index}",
                "port": 443,
                "uuid": f"00000000-0000-4000-8000-0000000000{40 + index}",
                "network": "tcp",
                "security": "tls",
                "tls": True,
                "source_subtype": "custom_manual",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
    package_id = _create_package(client, auth_headers, "按线路到期套餐")
    customer_id = _create_customer(client, auth_headers, "按线路到期客户")
    created = client.post(
        "/api/subscriptions",
        json={
            "package_id": package_id,
            "customer_id": customer_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    subscription_id = created.json()["id"]
    token = created.json()["token"]

    lines = client.get(
        f"/api/subscriptions/{subscription_id}/lines", headers=auth_headers
    )
    assert lines.status_code == 200
    assert len(lines.json()) == 2
    first_line = lines.json()[0]
    expired_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    updated = client.put(
        f"/api/subscriptions/{subscription_id}/lines/{first_line['id']}",
        json={"expires_at": expired_at},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "expired"

    response = client.get(f"/sub/{token}")
    assert response.status_code == 200
    assert "线路一 已到期，请及时续费" in response.text
    assert "198.51.100.41" in response.text


def test_package_with_customer_subscription_cannot_be_deleted(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    package_id = _create_package(client, auth_headers, "不可删除的客户套餐")
    customer_id = _create_customer(client, auth_headers, "客户丁")
    created = client.post(
        "/api/subscriptions",
        json={"package_id": package_id, "customer_id": customer_id},
        headers=auth_headers,
    )
    assert created.status_code == 201
    deleted = client.delete(f"/api/packages/{package_id}", headers=auth_headers)
    assert deleted.status_code == 400
    assert deleted.json()["detail"] == "套餐已有客户订阅，不能删除；请先停用套餐或处理客户订阅"


def test_subscription_lifecycle_renew_suspend_resume_cancel_and_cache_invalidation(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """续费和状态动作必须隔离、可回归，并立即影响订阅访问。"""

    _create_node(client, auth_headers, variant=1)
    package_id = _create_package(client, auth_headers, "生命周期套餐")
    customer_id = _create_customer(client, auth_headers, "生命周期客户")
    created = client.post(
        "/api/subscriptions",
        json={"package_id": package_id, "customer_id": customer_id, "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
        headers=auth_headers,
    )
    assert created.status_code == 201
    subscription_id = created.json()["id"]
    token = created.json()["token"]

    paused = client.post(f"/api/subscriptions/{subscription_id}/suspend", headers=auth_headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert client.get(f"/sub/{token}").status_code == 404

    resumed = client.post(f"/api/subscriptions/{subscription_id}/resume", headers=auth_headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"
    assert client.get(f"/sub/{token}").status_code == 200

    renewed = client.post(
        f"/api/subscriptions/{subscription_id}/renew",
        json={"days": 30},
        headers=auth_headers,
    )
    assert renewed.status_code == 200
    assert renewed.json()["status"] == "active"
    assert renewed.json()["expires_at"] > created.json()["expires_at"]

    cancelled = client.post(f"/api/subscriptions/{subscription_id}/cancel", headers=auth_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.get(f"/sub/{token}").status_code == 404
    rejected = client.post(
        f"/api/subscriptions/{subscription_id}/renew",
        json={"days": 30},
        headers=auth_headers,
    )
    assert rejected.status_code == 400

    notifications = client.get("/api/notifications", headers=auth_headers)
    assert notifications.status_code == 200
    lifecycle = [item for item in notifications.json()["items"] if item["kind"] == "subscription_lifecycle"]
    assert lifecycle
    assert all(item["subscription_id"] == subscription_id for item in lifecycle)


def _create_manager(client: TestClient, headers: dict[str, str], username: str) -> int:
    response = client.post(
        "/api/users",
        json={"username": username, "password": "ManagerPass123!", "role": "manager"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["role"] == "manager"
    return response.json()["id"]


def _login_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_manager_scope_and_idor_protection(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    manager_a = _create_manager(client, auth_headers, "manager-a")
    manager_b = _create_manager(client, auth_headers, "manager-b")
    customer_a = client.post(
        "/api/customers",
        json={"name": "经理甲客户", "manager_user_id": manager_a},
        headers=auth_headers,
    ).json()["id"]
    customer_b = client.post(
        "/api/customers",
        json={"name": "经理乙客户", "manager_user_id": manager_b},
        headers=auth_headers,
    ).json()["id"]
    package_id = _create_package(client, auth_headers, "经理隔离套餐")
    subscription_a = client.post(
        "/api/subscriptions",
        json={"customer_id": customer_a, "package_id": package_id},
        headers=auth_headers,
    )
    assert subscription_a.status_code == 201
    subscription_b = client.post(
        "/api/subscriptions",
        json={"customer_id": customer_b, "package_id": package_id},
        headers=auth_headers,
    )
    assert subscription_b.status_code == 201

    headers_a = _login_headers(client, "manager-a", "ManagerPass123!")
    customers = client.get("/api/customers", headers=headers_a)
    assert customers.status_code == 200
    assert [item["id"] for item in customers.json()] == [customer_a]
    subscriptions = client.get("/api/subscriptions", headers=headers_a)
    assert subscriptions.status_code == 200
    assert [item["id"] for item in subscriptions.json()] == [subscription_a.json()["id"]]
    assert client.get(
        f"/api/subscriptions/{subscription_b.json()['id']}", headers=headers_a
    ).status_code == 404
    package_list = client.get("/api/packages", headers=headers_a)
    assert package_list.status_code == 200
    assert all(item["subscription_url"] is None for item in package_list.json())
    shared_package = next(item for item in package_list.json() if item["id"] == package_id)
    assert [item["customer_id"] for item in shared_package["used_by_customers"]] == [customer_a]
    assert client.get("/api/customers", headers={}).status_code == 401

    headers_b = _login_headers(client, "manager-b", "ManagerPass123!")
    assert [item["id"] for item in client.get("/api/customers", headers=headers_b).json()] == [customer_b]


def test_customer_manager_transfer_migrates_subscription_access(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """客户转移或取消经理后，旧经理不能继续看到该客户订阅。"""

    manager_a = _create_manager(client, auth_headers, "transfer-manager-a")
    manager_b = _create_manager(client, auth_headers, "transfer-manager-b")
    customer = client.post(
        "/api/customers",
        json={"name": "转移客户", "manager_user_id": manager_a},
        headers=auth_headers,
    ).json()
    package_id = _create_package(client, auth_headers, "转移套餐")
    subscription = client.post(
        "/api/subscriptions",
        json={
            "customer_id": customer["id"],
            "package_id": package_id,
            "manager_user_id": manager_a,
        },
        headers=auth_headers,
    )
    assert subscription.status_code == 201
    headers_a = _login_headers(client, "transfer-manager-a", "ManagerPass123!")
    headers_b = _login_headers(client, "transfer-manager-b", "ManagerPass123!")

    transferred = client.put(
        f"/api/customers/{customer['id']}",
        json={"manager_user_id": manager_b},
        headers=auth_headers,
    )
    assert transferred.status_code == 200
    assert client.get("/api/subscriptions", headers=headers_a).json() == []
    assert [item["id"] for item in client.get("/api/subscriptions", headers=headers_b).json()] == [subscription.json()["id"]]

    cleared = client.put(
        f"/api/customers/{customer['id']}",
        json={"manager_user_id": None},
        headers=auth_headers,
    )
    assert cleared.status_code == 200
    assert client.get("/api/subscriptions", headers=headers_b).json() == []


def test_manager_can_share_node_only_from_active_owned_subscription(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """经理可以分享自己有效订阅的节点，失效订阅不能导出节点 URI。"""

    manager_id = _create_manager(client, auth_headers, "share-manager")
    customer = client.post(
        "/api/customers",
        json={"name": "分享客户", "manager_user_id": manager_id},
        headers=auth_headers,
    ).json()
    _create_node(client, auth_headers)
    package_id = _create_package(client, auth_headers, "分享套餐")
    subscription = client.post(
        "/api/subscriptions",
        json={"customer_id": customer["id"], "package_id": package_id},
        headers=auth_headers,
    )
    assert subscription.status_code == 201
    manager_headers = _login_headers(client, "share-manager", "ManagerPass123!")
    preview = client.get(
        f"/api/manager/subscriptions/{subscription.json()['id']}/preview",
        headers=manager_headers,
    )
    assert preview.status_code == 200
    node_id = preview.json()[0]["id"]
    shared = client.get(
        f"/api/manager/subscriptions/{subscription.json()['id']}/nodes/{node_id}/export",
        headers=manager_headers,
    )
    assert shared.status_code == 200
    assert shared.json()["content"].startswith("vless://")

    suspended = client.post(
        f"/api/subscriptions/{subscription.json()['id']}/suspend", headers=manager_headers
    )
    assert suspended.status_code == 200
    assert client.get(
        f"/api/manager/subscriptions/{subscription.json()['id']}/nodes/{node_id}/export",
        headers=manager_headers,
    ).status_code == 404


def test_subscription_manager_override_controls_subscription_scope(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """订阅指定经理后，订阅相关接口应按订阅经理隔离。"""

    manager_a = _create_manager(client, auth_headers, "override-manager-a")
    manager_b = _create_manager(client, auth_headers, "override-manager-b")
    customer = client.post(
        "/api/customers",
        json={"name": "默认归属经理甲", "manager_user_id": manager_a},
        headers=auth_headers,
    ).json()["id"]
    package_id = _create_package(client, auth_headers, "订阅经理覆盖套餐")
    subscription = client.post(
        "/api/subscriptions",
        json={
            "customer_id": customer,
            "package_id": package_id,
            "manager_user_id": manager_b,
        },
        headers=auth_headers,
    )
    assert subscription.status_code == 201
    subscription_id = subscription.json()["id"]

    headers_a = _login_headers(client, "override-manager-a", "ManagerPass123!")
    headers_b = _login_headers(client, "override-manager-b", "ManagerPass123!")

    assert client.get("/api/subscriptions", headers=headers_a).json() == []
    assert client.get(
        f"/api/subscriptions/{subscription_id}", headers=headers_a
    ).status_code == 404
    assert client.post(
        f"/api/subscriptions/{subscription_id}/regenerate-token", headers=headers_a
    ).status_code == 404

    visible = client.get("/api/subscriptions", headers=headers_b)
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()] == [subscription_id]
    assert visible.json()[0]["manager_user_id"] == manager_b
    assert visible.json()[0]["manager_username"] == "override-manager-b"

    package = client.get("/api/packages", headers=headers_b)
    assert package.status_code == 200
    usage = next(item for item in package.json() if item["id"] == package_id)[
        "used_by_customers"
    ]
    assert [item["customer_id"] for item in usage] == [customer]

    customers_b = client.get("/api/customers", headers=headers_b)
    assert customers_b.status_code == 200
    assert [item["id"] for item in customers_b.json()] == [customer]
    assert client.get("/api/customers", headers=headers_a).json() == []


def test_manager_assignment_rejects_non_manager_and_can_be_cleared(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    customer = client.post(
        "/api/customers", json={"name": "负责人校验客户"}, headers=auth_headers
    ).json()["id"]
    user = client.post(
        "/api/users",
        json={"username": "not-manager", "password": "ViewerPass123!"},
        headers=auth_headers,
    ).json()["id"]
    rejected = client.put(
        f"/api/customers/{customer}",
        json={"manager_user_id": user},
        headers=auth_headers,
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "经理不存在或已停用"


def test_expiry_notifications_are_scoped_and_idempotent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    manager_id = _create_manager(client, auth_headers, "notification-manager")
    customer = client.post(
        "/api/customers",
        json={"name": "提醒客户", "manager_user_id": manager_id},
        headers=auth_headers,
    ).json()["id"]
    package_id = _create_package(client, auth_headers, "提醒套餐")
    created = client.post(
        "/api/subscriptions",
        json={
            "customer_id": customer,
            "package_id": package_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
        headers=auth_headers,
    )
    assert created.status_code == 201

    manager_headers = _login_headers(
        client, "notification-manager", "ManagerPass123!"
    )
    first = client.get("/api/notifications?kind=subscription_expiry", headers=manager_headers)
    assert first.status_code == 200
    assert first.json()["unread_count"] == 1
    assert len(first.json()["items"]) == 1
    notification_id = first.json()["items"][0]["id"]
    assert created.json()["token"] not in first.text
    assert "北京时间" in first.json()["items"][0]["content"]
    assert "UTC" not in first.json()["items"][0]["content"]

    second = client.get("/api/notifications?kind=subscription_expiry", headers=manager_headers)
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["unread_count"] == 1

    marked = client.post(
        f"/api/notifications/{notification_id}/read", headers=manager_headers
    )
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None
    assert client.get("/api/notifications?kind=subscription_expiry", headers=manager_headers).json()["unread_count"] == 0

    admin_inbox = client.get("/api/notifications?kind=subscription_expiry", headers=auth_headers)
    assert admin_inbox.status_code == 200
    admin_items = admin_inbox.json()["items"]
    assert len(admin_items) == 1
    assert admin_items[0]["id"] != notification_id

    unread = client.get(
        "/api/notifications?status=all&kind=subscription_expiry&page=1&page_size=1", headers=manager_headers
    )
    assert unread.status_code == 200
    assert unread.json()["total"] == 1
    assert unread.json()["pages"] == 1
    archived = client.post(
        f"/api/notifications/{notification_id}/archive", headers=manager_headers
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None


def test_manager_has_separate_login_and_can_manage_own_customers(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/users",
        json={"username": "separate-manager", "password": "ManagerPass123!", "role": "manager"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    login = client.post(
        "/api/manager/login",
        json={"username": "separate-manager", "password": "ManagerPass123!"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "manager"
    manager_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    customer = client.post(
        "/api/customers", json={"name": "经理客户"}, headers=manager_headers
    )
    assert customer.status_code == 201
    assert customer.json()["manager_username"] == "separate-manager"
    assert client.get("/api/customers", headers=manager_headers).json()[0]["id"] == customer.json()["id"]


def test_manager_can_create_update_and_clear_customer_notes(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """经理可以维护自己客户和客户订阅的备注，且清空后不会留下空白字符串。"""

    manager_id = _create_manager(client, auth_headers, "note-manager")
    customer = client.post(
        "/api/customers",
        json={"name": "备注客户", "manager_user_id": manager_id, "note": "管理员备注"},
        headers=auth_headers,
    )
    assert customer.status_code == 201
    package_id = _create_package(client, auth_headers, "备注套餐")
    subscription = client.post(
        "/api/subscriptions",
        json={"customer_id": customer.json()["id"], "package_id": package_id, "note": "初始订阅备注"},
        headers=auth_headers,
    )
    assert subscription.status_code == 201

    manager_headers = _login_headers(client, "note-manager", "ManagerPass123!")
    updated_customer = client.put(
        f"/api/customers/{customer.json()['id']}",
        json={"note": "经理跟进备注"},
        headers=manager_headers,
    )
    assert updated_customer.status_code == 200
    assert updated_customer.json()["note"] == "经理跟进备注"

    updated_subscription = client.put(
        f"/api/subscriptions/{subscription.json()['id']}",
        json={"note": "客户偏好香港线路"},
        headers=manager_headers,
    )
    assert updated_subscription.status_code == 200
    assert updated_subscription.json()["note"] == "客户偏好香港线路"

    cleared = client.put(
        f"/api/subscriptions/{subscription.json()['id']}",
        json={"note": "   "},
        headers=manager_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["note"] is None


def test_admin_can_lookup_customer_and_legacy_package_by_token_or_url(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """管理员可以用 Token 或订阅链接找回两类订阅记录，经理不能使用该入口。"""

    customer_id = _create_customer(client, auth_headers, "查找客户")
    legacy_package = client.post(
        "/api/packages",
        json={"name": "查找套餐", "description": "历史套餐说明", "rules": {"node_ids": []}},
        headers=auth_headers,
    )
    assert legacy_package.status_code == 201
    package_id = legacy_package.json()["id"]
    subscription = client.post(
        "/api/subscriptions",
        json={"customer_id": customer_id, "package_id": package_id, "note": "待补备注"},
        headers=auth_headers,
    )
    assert subscription.status_code == 201
    token = subscription.json()["token"]
    url = subscription.json()["subscription_url"]

    found_by_token = client.post(
        "/api/subscriptions/lookup", json={"query": token}, headers=auth_headers
    )
    assert found_by_token.status_code == 200
    assert found_by_token.json()["kind"] == "customer_subscription"
    assert found_by_token.json()["customer_name"] == "查找客户"
    assert token not in found_by_token.text

    found_by_url = client.post(
        "/api/subscriptions/lookup", json={"query": url + "?client=clash"}, headers=auth_headers
    )
    assert found_by_url.status_code == 200
    assert found_by_url.json()["id"] == subscription.json()["id"]

    package_lookup = client.get(
        "/api/packages/lookup",
        params={"query": url + "?client=clash"},
        headers=auth_headers,
    )
    assert package_lookup.status_code == 200
    assert package_lookup.json()[0]["package_id"] == package_id
    assert package_lookup.json()[0]["customer_name"] == "查找客户"
    assert token not in package_lookup.text

    legacy_lookup = client.post(
        "/api/subscriptions/lookup",
        json={"query": legacy_package.json()["token"]},
        headers=auth_headers,
    )
    assert legacy_lookup.status_code == 200
    assert legacy_lookup.json()["kind"] == "package"
    assert legacy_lookup.json()["package_name"] == "查找套餐"

    manager_id = _create_manager(client, auth_headers, "lookup-manager")
    manager_headers = _login_headers(client, "lookup-manager", "ManagerPass123!")
    assert client.post(
        "/api/subscriptions/lookup", json={"query": token}, headers=manager_headers
    ).status_code == 403


def test_subscription_token_modes_and_history_restore(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """三种 Token 策略都能创建，轮换后的历史 Token 可由管理员恢复。"""

    _create_node(client, auth_headers)
    customer_id = _create_customer(client, auth_headers, "Token 策略客户")
    package_id = _create_package(client, auth_headers, "Token 策略套餐")
    custom_token = "manual-token-123456"
    created = client.post(
        "/api/subscriptions",
        json={
            "customer_id": customer_id,
            "package_id": package_id,
            "token_mode": "manual",
            "custom_token": custom_token,
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    assert created.json()["token"] == custom_token
    assert created.json()["token_mode"] == "manual"

    subscription_id = created.json()["id"]
    rotated = client.post(
        f"/api/subscriptions/{subscription_id}/regenerate-token", headers=auth_headers
    )
    assert rotated.status_code == 200
    assert rotated.json()["token"] != custom_token
    assert client.get(f"/sub/{custom_token}").status_code == 404

    history = client.get(
        f"/api/subscriptions/{subscription_id}/token-history", headers=auth_headers
    )
    assert history.status_code == 200
    history_rows = history.json()
    assert len(history_rows) == 2
    assert any(row["token_prefix"] == custom_token[:8] and row["valid_to"] for row in history_rows)
    assert custom_token not in history.text

    old_version = next(row for row in history_rows if row["token_prefix"] == custom_token[:8])
    restored = client.post(
        f"/api/subscriptions/{subscription_id}/restore-token",
        json={"version_id": old_version["id"], "reason": "误操作恢复"},
        headers=auth_headers,
    )
    assert restored.status_code == 200
    assert restored.json()["token"] == custom_token
    assert restored.json()["token_mode"] == "restored"
    assert client.get(f"/sub/{custom_token}").status_code == 200

    lookup = client.post(
        "/api/subscriptions/lookup", json={"query": custom_token}, headers=auth_headers
    )
    assert lookup.status_code == 200
    assert lookup.json()["historical"] is False


def test_package_token_can_only_be_taken_over_once(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """套餐 Token 接管后屏蔽旧套餐入口，且不能被第二个客户并行使用。"""

    _create_node(client, auth_headers)
    package_id = _create_package(client, auth_headers, "一次性接管套餐")
    package_url = client.get(
        f"/api/packages/{package_id}/subscription-url", headers=auth_headers
    )
    assert package_url.status_code == 200
    package_token = package_url.json()["subscription_url"].rsplit("/", 1)[-1]
    customer_a = _create_customer(client, auth_headers, "接管客户甲")
    customer_b = _create_customer(client, auth_headers, "接管客户乙")

    taken_over = client.post(
        "/api/subscriptions",
        json={"customer_id": customer_a, "package_id": package_id, "token_mode": "package"},
        headers=auth_headers,
    )
    assert taken_over.status_code == 201
    assert taken_over.json()["token"] == package_token
    assert client.get(f"/sub/{package_token}").status_code == 200

    second_takeover = client.post(
        "/api/subscriptions",
        json={"customer_id": customer_b, "package_id": package_id, "token_mode": "package"},
        headers=auth_headers,
    )
    assert second_takeover.status_code == 400


def test_manager_cannot_restore_subscription_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Token 历史可查看，但恢复属于管理员高风险操作。"""

    manager_id = _create_manager(client, auth_headers, "token-history-manager")
    customer = client.post(
        "/api/customers",
        json={"name": "Token 历史经理客户", "manager_user_id": manager_id},
        headers=auth_headers,
    ).json()
    package_id = _create_package(client, auth_headers, "Token 历史权限套餐")
    created = client.post(
        "/api/subscriptions",
        json={"customer_id": customer["id"], "package_id": package_id},
        headers=auth_headers,
    ).json()
    client.post(
        f"/api/subscriptions/{created['id']}/regenerate-token", headers=auth_headers
    )
    history = client.get(
        f"/api/subscriptions/{created['id']}/token-history", headers=auth_headers
    ).json()
    old_version = next(row for row in history if row["valid_to"])
    manager_headers = _login_headers(client, "token-history-manager", "ManagerPass123!")
    assert client.post(
        f"/api/subscriptions/{created['id']}/restore-token",
        json={"version_id": old_version["id"]},
        headers=manager_headers,
    ).status_code == 403


def test_notification_idor_is_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    manager_a = _create_manager(client, auth_headers, "notification-a")
    manager_b = _create_manager(client, auth_headers, "notification-b")
    customer = client.post(
        "/api/customers",
        json={"name": "隔离提醒客户", "manager_user_id": manager_a},
        headers=auth_headers,
    ).json()["id"]
    package_id = _create_package(client, auth_headers, "隔离提醒套餐")
    assert client.post(
        "/api/subscriptions",
        json={
            "customer_id": customer,
            "package_id": package_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        headers=auth_headers,
    ).status_code == 201
    headers_a = _login_headers(client, "notification-a", "ManagerPass123!")
    notification_id = client.get("/api/notifications", headers=headers_a).json()["items"][0]["id"]
    headers_b = _login_headers(client, "notification-b", "ManagerPass123!")
    assert client.post(
        f"/api/notifications/{notification_id}/read", headers=headers_b
    ).status_code == 404


def test_manager_stats_and_subscription_preview_are_scoped(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    manager_a = _create_manager(client, auth_headers, "stats-manager-a")
    manager_b = _create_manager(client, auth_headers, "stats-manager-b")
    customer_a = client.post(
        "/api/customers",
        json={"name": "统计客户甲", "region": "香港", "manager_user_id": manager_a},
        headers=auth_headers,
    ).json()["id"]
    customer_b = client.post(
        "/api/customers",
        json={"name": "统计客户乙", "region": "日本", "manager_user_id": manager_b},
        headers=auth_headers,
    ).json()["id"]
    package_id = _create_package(client, auth_headers, "统计套餐")
    subscription_a = client.post(
        "/api/subscriptions",
        json={"customer_id": customer_a, "package_id": package_id, "sale_price": "88.00"},
        headers=auth_headers,
    )
    subscription_b = client.post(
        "/api/subscriptions",
        json={"customer_id": customer_b, "package_id": package_id, "sale_price": "99.00"},
        headers=auth_headers,
    )
    assert subscription_a.status_code == 201
    assert subscription_b.status_code == 201

    manager_headers = _login_headers(client, "stats-manager-a", "ManagerPass123!")
    stats = client.get("/api/manager/stats", headers=manager_headers)
    assert stats.status_code == 200
    assert stats.json()["customer_count"] == 1
    assert stats.json()["active_subscription_count"] == 1
    assert stats.json()["sales_total"] == "88.00"
    assert stats.json()["regions"] == [{"region": "香港", "customer_count": 1}]

    health = client.get("/api/manager/health", headers=manager_headers)
    assert health.status_code == 200
    assert health.json() == []
    manager_logs = client.get("/api/logs/manager", headers=manager_headers)
    assert manager_logs.status_code == 200
    assert all(item["admin_user_id"] == manager_a for item in manager_logs.json()["items"])

    preview = client.get(
        f"/api/manager/subscriptions/{subscription_a.json()['id']}/preview",
        headers=manager_headers,
    )
    assert preview.status_code == 200
    assert all("uuid" not in node and "password" not in node for node in preview.json())
    assert client.get(
        f"/api/manager/subscriptions/{subscription_b.json()['id']}/preview",
        headers=manager_headers,
    ).status_code == 404
