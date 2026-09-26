"""安全配置与敏感值加解密测试。"""

from __future__ import annotations

import logging
from io import StringIO
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core import config
from app.core.logging import RedactingFormatter, SensitiveFilter, setup_logging
from app.core.rate_limit import rate_limiter
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


def test_production_requires_fixed_jwt_secret(monkeypatch) -> None:
    """生产环境缺少固定 JWT 密钥时必须拒绝启动。"""

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    monkeypatch.setattr(config, "_settings", None)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        config.get_settings()


def test_production_requires_admin_password_and_public_https_url(monkeypatch) -> None:
    """生产环境必须明确配置管理员密码和外部 HTTPS 地址。"""

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "fixed-production-secret-1234567890")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setattr(config, "_settings", None)

    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        config.get_settings()

    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://example.com")
    monkeypatch.setattr(config, "_settings", None)
    with pytest.raises(RuntimeError, match="HTTPS"):
        config.get_settings()


def test_production_wildcard_cors_is_restricted_to_public_origin(monkeypatch) -> None:
    """生产环境未显式配置 CORS 时只能允许公开站点来源。"""

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "fixed-production-secret-1234567890")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://sub.example.com")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setattr(config, "_settings", None)

    settings = config.get_settings()

    assert settings.cors_origins == "https://sub.example.com"


def test_production_rejects_weak_or_unsupported_jwt_configuration(monkeypatch) -> None:
    """生产环境不得使用过短密钥或不受支持的 JWT 算法。"""

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "short-secret")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://sub.example.com")
    monkeypatch.setattr(config, "_settings", None)
    with pytest.raises(RuntimeError, match="32"):
        config.get_settings()

    monkeypatch.setenv("JWT_SECRET_KEY", "fixed-production-secret-1234567890")
    monkeypatch.setenv("JWT_ALGORITHM", "none")
    monkeypatch.setattr(config, "_settings", None)
    with pytest.raises(RuntimeError, match="JWT_ALGORITHM"):
        config.get_settings()


def test_nginx_does_not_receive_application_dotenv_secrets() -> None:
    """Nginx 只接收环境模式，不应继承 API 的 JWT 或管理员密码。"""

    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    nginx = compose["services"]["nginx"]
    assert "env_file" not in nginx
    assert nginx["environment"] == ["APP_ENV=${APP_ENV:-development}"]
    for config_name in ("nginx.conf", "nginx-https.conf"):
        nginx_config = (
            compose_path.parent / "deploy" / "nginx" / config_name
        ).read_text(encoding="utf-8")
        assert "location /sub/" in nginx_config
        assert "access_log off;" in nginx_config


def test_validation_errors_do_not_echo_sensitive_input(client: TestClient) -> None:
    """422 响应不得回显请求中的密码或 Token。"""

    secret = "password-that-must-not-leak"
    login = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert login.status_code == 200
    response = client.post(
        "/api/nodes",
        json={"name": {"secret": secret}, "type": "vless", "server": "example.com", "port": 443},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 422
    assert secret not in response.text
    assert '"input"' not in response.text


def test_sensitive_log_filter_redacts_credentials_and_node_uris() -> None:
    """日志保留诊断信息，但不得包含完整凭据、Token 或节点 URI。"""

    secret_values = {
        "jwt": "eyJhbGciOiJIUzI1NiJ9.secret-payload.signature-value",
        "token": "subscription-token-secret-123",
        "uuid": "00000000-0000-0000-0000-000000000999",
        "password": "ss-password-secret",
        "query": "upstream-query-secret",
        "spaced_password": "password with spaces",
    }
    message = (
        "Authorization: Bearer {jwt} token={token} uuid={uuid} "
        "password={password} url=https://user:pass@example.com/sub?token={query} "
        "password='{spaced_password}' vless://{uuid}@node.example.com:443?password={password}"
    ).format(**secret_values)
    record = logging.LogRecord("test", logging.WARNING, __file__, 1, message, (), None)

    assert SensitiveFilter().filter(record) is True
    filtered = record.getMessage()
    for value in secret_values.values():
        assert value not in filtered
    assert "[REDACTED" in filtered


def test_setup_logging_attaches_filter_to_existing_root_handlers() -> None:
    """运行器预先配置 root handler 时，仍然必须安装脱敏过滤器。"""

    root = logging.getLogger()
    access_logger = logging.getLogger("uvicorn.access")
    original_handlers = root.handlers[:]
    original_access_handlers = access_logger.handlers[:]
    original_level = root.level
    handler = logging.StreamHandler(StringIO())
    access_handler = logging.StreamHandler(StringIO())
    root.handlers = [handler]
    access_logger.handlers = [access_handler]
    try:
        setup_logging()
        assert any(isinstance(item, SensitiveFilter) for item in handler.filters)
        assert any(isinstance(item, SensitiveFilter) for item in access_handler.filters)
        record = logging.LogRecord(
            "test",
            logging.INFO,
            __file__,
            1,
            "password=must-not-appear",
            (),
            None,
        )
        handler.handle(record)
        assert "must-not-appear" not in handler.stream.getvalue()
    finally:
        root.handlers = original_handlers
        access_logger.handlers = original_access_handlers
        root.setLevel(original_level)


def test_sensitive_filter_preserves_structured_log_arguments() -> None:
    """脱敏不能破坏 Uvicorn 访问日志依赖的结构化参数。"""

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %s',
        ("127.0.0.1:1234", "GET", "/sub/secret-token", "1.1", "200"),
        None,
    )
    assert SensitiveFilter().filter(record) is True
    assert record.args

    handler = logging.StreamHandler(StringIO())
    handler.setFormatter(RedactingFormatter(logging.Formatter("%(message)s")))
    handler.addFilter(SensitiveFilter())
    handler.handle(record)

    assert "secret-token" not in handler.stream.getvalue()


def test_login_rate_limit_returns_uniform_error_and_retry_after(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """连续失败登录达到阈值后应返回统一错误，不泄漏认证细节。"""

    rate_limiter.clear_all()
    settings = config.get_settings()
    monkeypatch.setattr(settings, "login_rate_limit", 2)
    monkeypatch.setattr(settings, "login_rate_window_seconds", 60)

    for _ in range(2):
        response = client.post(
            "/api/admin/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        assert response.status_code == 401

    limited = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert limited.status_code == 429
    assert limited.json()["detail"] == "请求过于频繁，请稍后再试"
    assert limited.headers["retry-after"]


def test_successful_login_clears_failed_login_counter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """成功登录后失败计数应清零，避免正常用户被历史失败请求锁定。"""

    rate_limiter.clear_all()
    settings = config.get_settings()
    monkeypatch.setattr(settings, "login_rate_limit", 2)
    monkeypatch.setattr(settings, "login_rate_window_seconds", 60)

    failed = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert failed.status_code == 401
    success = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert success.status_code == 200
    for _ in range(2):
        failed = client.post(
            "/api/admin/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        assert failed.status_code == 401
