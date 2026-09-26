"""管理员认证接口测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db import SessionLocal
from app.models.user import User

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


def test_non_admin_role_cannot_use_admin_apis(client: TestClient) -> None:
    """JWT 对应的活跃非管理员用户不能访问后台管理接口。"""

    username = "viewer-security-test"
    db = SessionLocal()
    try:
        db.add(
            User(
                username=username,
                password_hash=hash_password("ViewerPass123!"),
                role="viewer",
            )
        )
        db.commit()
    finally:
        db.close()

    token = create_access_token(username)
    response = client.get("/api/packages", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "权限不足"


def test_user_login_returns_user_role_and_cannot_use_admin_login(client: TestClient) -> None:
    """普通用户应从通用入口登录，管理员入口不能发放管理员会话。"""

    create_response = client.post(
        "/api/users",
        json={"username": "normal-login-user", "password": "UserPass123!"},
        headers={"Authorization": f"Bearer {_login(client)}"},
    )
    assert create_response.status_code == 201

    admin_login = client.post(
        LOGIN_URL,
        json={"username": "normal-login-user", "password": "UserPass123!"},
    )
    assert admin_login.status_code == 401

    user_login = client.post(
        "/api/auth/login",
        json={"username": "normal-login-user", "password": "UserPass123!"},
    )
    assert user_login.status_code == 200
    assert user_login.json()["role"] == "user"
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {user_login.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "normal-login-user"


def test_admin_can_update_username_and_password(client: TestClient) -> None:
    """管理员修改用户名后旧 subject 失效，新用户名可以登录。"""

    old_token = _login(client)
    response = client.put(
        "/api/admin/profile",
        json={
            "current_password": ORIGINAL_PASSWORD,
            "username": "renamed-admin",
        },
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "renamed-admin"

    assert client.get(
        ME_URL, headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 401
    new_token = client.post(
        LOGIN_URL,
        json={"username": "renamed-admin", "password": ORIGINAL_PASSWORD},
    ).json()["access_token"]
    assert client.put(
        "/api/admin/profile",
        json={"current_password": ORIGINAL_PASSWORD, "username": ADMIN_USERNAME},
        headers={"Authorization": f"Bearer {new_token}"},
    ).status_code == 200


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
