"""安全工具：密码哈希、JWT、Token 哈希与脱敏。"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """使用 bcrypt 生成密码哈希。"""

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配。"""

    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str) -> str:
    """生成管理员 JWT。"""

    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """解码 JWT 并返回 subject；无效或过期时抛出异常。"""

    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise jwt.InvalidTokenError("JWT subject 缺失")
    return subject


def generate_subscription_token() -> str:
    """生成高强度订阅 Token。"""

    return secrets.token_urlsafe(32)


def hash_subscription_token(token: str) -> str:
    """计算订阅 Token 的 SHA-256 哈希，数据库只保存哈希。"""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_prefix(token: str, length: int = 8) -> str:
    """返回 Token 前若干位，仅用于后台展示。"""

    return token[:length]


def mask_secret(value: str, keep_head: int = 6, keep_tail: int = 4) -> str:
    """对敏感字段脱敏，保留首尾少量字符便于辨认。"""

    if not value:
        return ""
    if len(value) <= keep_head + keep_tail:
        return "*" * len(value)
    return f"{value[:keep_head]}...{value[-keep_tail:]}"
