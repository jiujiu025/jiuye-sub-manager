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
        if repo.get_by_username(settings.admin_username) is not None:
            return
        password = settings.admin_password
        if not password:
            password = secrets.token_urlsafe(12)
            # 一次性临时密码直接打印到控制台，不经过日志脱敏过滤器
            print(f"[首次启动] 管理员 {settings.admin_username} 临时密码：{password}", flush=True)
            logger.warning("未配置 ADMIN_PASSWORD，已生成一次性临时密码，请尽快登录后台修改")
        user = repo.create(settings.admin_username, hash_password(password))
        db.add(user)
        db.commit()
    finally:
        db.close()
