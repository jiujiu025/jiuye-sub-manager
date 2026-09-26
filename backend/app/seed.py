"""初始化管理员账号。"""

from __future__ import annotations

import logging
import secrets

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


def ensure_admin() -> None:
    """数据库不存在管理员时创建；未配置密码则生成一次性临时密码。"""

    settings = get_settings()
    db = SessionLocal()
    try:
        repo = UserRepository(db)
        if repo.get_any_admin() is not None:
            return
        password = settings.admin_password
        if not password:
            if settings.app_env.strip().lower() in {"production", "prod"}:
                raise RuntimeError("生产环境必须配置 ADMIN_PASSWORD")
            password = secrets.token_urlsafe(12)
            # 不把临时密码写入日志；开发环境仍保留原有自动创建行为。
            logger.warning(
                "未配置 ADMIN_PASSWORD，已生成一次性临时密码；请通过安全渠道配置固定密码"
            )
        user = repo.create(settings.admin_username, hash_password(password))
        db.add(user)
        db.commit()
    finally:
        db.close()
