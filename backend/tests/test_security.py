"""安全配置与敏感值加解密测试。"""

from __future__ import annotations

from app.core import config
from app.core.security import create_access_token, decrypt_secret, encrypt_secret


def test_fixed_jwt_secret_survives_settings_reload(monkeypatch) -> None:
    """同一固定 JWT_SECRET_KEY 在配置重载后仍可解密 Token 并验证 JWT。"""

    fixed_secret = "fixed-test-secret-that-is-not-a-real-secret"
    monkeypatch.setenv("JWT_SECRET_KEY", fixed_secret)
    monkeypatch.setattr(config, "_settings", None)
    first_settings = config.get_settings()
    encrypted = encrypt_secret("subscription-token")
    jwt_token = create_access_token("admin")

    monkeypatch.setattr(config, "_settings", None)
    second_settings = config.get_settings()

    assert first_settings.jwt_secret_key == fixed_secret
    assert second_settings.jwt_secret_key == fixed_secret
    assert decrypt_secret(encrypted) == "subscription-token"
    assert config.get_settings().jwt_secret_key == fixed_secret

    import jwt

    assert jwt.decode(jwt_token, second_settings.jwt_secret_key, algorithms=["HS256"])["sub"] == "admin"
