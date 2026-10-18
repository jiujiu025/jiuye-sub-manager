"""客户账号绑定与客户门户隔离测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _customer(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post(
        "/api/customers", json={"name": name, "region": "香港"}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["id"]


def _package(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post(
        "/api/packages", json={"name": name}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_customer_account_can_be_created_and_portal_is_scoped(
    client: TestClient,
) -> None:
    admin_headers = _admin_headers(client)
    customer_a = _customer(client, admin_headers, "门户客户甲")
    customer_b = _customer(client, admin_headers, "门户客户乙")

    account = client.post(
        f"/api/customers/{customer_a}/account/create",
        json={"username": "portal-customer-a", "password": "PortalPass123!"},
        headers=admin_headers,
    )
    assert account.status_code == 200
    assert account.json()["account_username"] == "portal-customer-a"

    package_id = _package(client, admin_headers, "门户套餐")
    first = client.post(
        "/api/subscriptions",
        json={
            "customer_id": customer_a,
            "package_id": package_id,
            "sale_price": "99.00",
            "company_cost_price": "20.00",
            "sales_cost_price": "60.00",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
        headers=admin_headers,
    )
    assert first.status_code == 201
    second = client.post(
        "/api/subscriptions",
        json={"customer_id": customer_b, "package_id": package_id},
        headers=admin_headers,
    )
    assert second.status_code == 201

    customer_headers = _user_headers(
        client, "portal-customer-a", "PortalPass123!"
    )
    profile = client.get("/api/customer/me", headers=customer_headers)
    assert profile.status_code == 200
    assert profile.json() == {
        "bound": True,
        "customer_id": customer_a,
        "name": "门户客户甲",
        "region": "香港",
        "manager_username": None,
    }

    subscriptions = client.get("/api/customer/subscriptions", headers=customer_headers)
    assert subscriptions.status_code == 200
    payload = subscriptions.json()
    assert [item["id"] for item in payload] == [first.json()["id"]]
    assert "sale_price" not in payload[0]
    assert "company_cost_price" not in payload[0]
    assert "sales_cost_price" not in payload[0]

    notifications = client.get(
        "/api/customer/notifications?status=unread&kind=subscription_expiry",
        headers=customer_headers,
    )
    assert notifications.status_code == 200
    assert notifications.json()["total"] == 1
    assert notifications.json()["items"][0]["subscription_id"] == first.json()["id"]

    own = client.get(
        f"/api/customer/subscriptions/{first.json()['id']}", headers=customer_headers
    )
    assert own.status_code == 200
    assert client.get(
        f"/api/customer/subscriptions/{second.json()['id']}", headers=customer_headers
    ).status_code == 404

    url = client.get(
        f"/api/customer/subscriptions/{first.json()['id']}/subscription-url",
        headers=customer_headers,
    )
    assert url.status_code == 200
    assert "/sub/" in url.json()["subscription_url"]


def test_customer_account_bind_rejects_manager_and_unbinds_without_deleting_user(
    client: TestClient,
) -> None:
    admin_headers = _admin_headers(client)
    customer_id = _customer(client, admin_headers, "绑定校验客户")
    manager = client.post(
        "/api/users",
        json={"username": "portal-manager", "password": "ManagerPass123!", "role": "manager"},
        headers=admin_headers,
    )
    assert manager.status_code == 201
    manager_login = client.post(
        "/api/manager/login",
        json={"username": "portal-manager", "password": "ManagerPass123!"},
    )
    assert manager_login.status_code == 200
    manager_headers = {
        "Authorization": f"Bearer {manager_login.json()['access_token']}"
    }
    assert client.get("/api/customer/me", headers=manager_headers).status_code == 403
    assert client.post(
        f"/api/customers/{customer_id}/account/bind",
        json={"user_id": manager.json()["id"]},
        headers=admin_headers,
    ).status_code == 400

    user = client.post(
        "/api/users",
        json={"username": "portal-unbind-user", "password": "UserPass123!"},
        headers=admin_headers,
    )
    assert user.status_code == 201
    bound = client.post(
        f"/api/customers/{customer_id}/account/bind",
        json={"user_id": user.json()["id"]},
        headers=admin_headers,
    )
    assert bound.status_code == 200
    assert client.delete(
        f"/api/customers/{customer_id}/account", headers=admin_headers
    ).status_code == 200
    assert client.post(
        "/api/auth/login",
        json={"username": "portal-unbind-user", "password": "UserPass123!"},
    ).status_code == 200

    unbound_headers = _user_headers(client, "portal-unbind-user", "UserPass123!")
    assert client.get("/api/customer/me", headers=unbound_headers).json() == {
        "bound": False,
        "customer_id": None,
        "name": None,
        "region": None,
        "manager_username": None,
    }


def test_expired_customer_subscription_cannot_preview_real_nodes(
    client: TestClient,
) -> None:
    admin_headers = _admin_headers(client)
    customer_id = _customer(client, admin_headers, "过期预览客户")
    account = client.post(
        f"/api/customers/{customer_id}/account/create",
        json={"username": "expired-preview-customer", "password": "PortalPass123!"},
        headers=admin_headers,
    )
    assert account.status_code == 200
    package_id = _package(client, admin_headers, "过期预览套餐")
    subscription = client.post(
        "/api/subscriptions",
        json={
            "customer_id": customer_id,
            "package_id": package_id,
            "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
        headers=admin_headers,
    )
    assert subscription.status_code == 201
    customer_headers = _user_headers(
        client, "expired-preview-customer", "PortalPass123!"
    )

    subscriptions = client.get("/api/customer/subscriptions", headers=customer_headers)
    assert subscriptions.status_code == 200
    assert subscriptions.json()[0]["status"] == "expired"

    preview = client.get(
        f"/api/customer/subscriptions/{subscription.json()['id']}/preview",
        headers=customer_headers,
    )
    assert preview.status_code == 404
