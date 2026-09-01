"""管理员认证接口测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

LOGIN_URL = "/api/admin/login"
ME_URL = "/api/admin/me"
PASSWORD_URL = "/api/admin/password"
ADMIN_USERNAME = "admin"
ORIGINAL_PASSWORD = "TestPass123!"
NEW_PASSWORD = "NewPass456!"


def _login(client: TestClient, password: str = ORIGINAL_PASSWORD) -> str:
    response = client.post(
        LOGIN_URL,
        json={"username": ADMIN_USERNAME, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_success(client: TestClient) -> None:
    """正确密码应返回 JWT。"""

    token = _login(client)
    assert len(token) > 20


def test_login_wrong_password(client: TestClient) -> None:
    """错误密码应返回 401 且不泄漏账号信息。"""

    response = client.post(
        LOGIN_URL,
        json={"username": ADMIN_USERNAME, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "用户名或密码错误"


def test_me_without_token(client: TestClient) -> None:
    """未携带 Token 访问受保护接口应返回 401。"""

    response = client.get(ME_URL)
    assert response.status_code == 401


def test_me_with_token(client: TestClient) -> None:
    """携带有效 Token 应返回管理员信息。"""

    token = _login(client)
    response = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == ADMIN_USERNAME


def test_me_with_invalid_token(client: TestClient) -> None:
    """伪造 Token 应返回 401。"""

    response = client.get(ME_URL, headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401


def test_change_password_and_revert(client: TestClient) -> None:
    """修改密码后旧密码失效、新密码可登录，最后改回原密码。"""

    old_token = _login(client)
    response = client.put(
        PASSWORD_URL,
        json={"old_password": ORIGINAL_PASSWORD, "new_password": NEW_PASSWORD},
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert response.status_code == 200

    # 旧密码应失效
    response = client.post(
        LOGIN_URL,
        json={"username": ADMIN_USERNAME, "password": ORIGINAL_PASSWORD},
    )
    assert response.status_code == 401

    # 新密码可登录，再改回原密码
    new_token = _login(client, NEW_PASSWORD)
    response = client.put(
        PASSWORD_URL,
        json={"old_password": NEW_PASSWORD, "new_password": ORIGINAL_PASSWORD},
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/sources",
        "/api/nodes",
        "/api/packages",
        "/api/logs?kind=sync",
        "/api/dashboard/stats",
        "/api/system/settings",
    ],
)
def test_all_backend_apis_require_auth(client: TestClient, path: str) -> None:
    """所有后台管理接口未登录时必须返回 401。"""

    response = client.get(path)
    assert response.status_code == 401
