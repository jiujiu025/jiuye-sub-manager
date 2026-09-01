"""应用配置：统一从环境变量和 .env 文件读取。"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """全局配置模型，字段名与 .env 中的键一一对应。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "订阅聚合与节点分发系统"
    database_url: str = "sqlite:///./data/sub_manager.db"
    jwt_secret_key: str = ""
    jwt_expire_minutes: int = 720
    jwt_algorithm: str = "HS256"
    admin_username: str = "admin"
    admin_password: str = ""
    sync_interval_minutes: int = 5
    sync_enabled: bool = True
    cache_ttl_seconds: int = 300
    http_timeout_seconds: float = 15.0
    cors_origins: str = "*"
    public_base_url: str = "http://localhost:8000"


_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置单例；未配置 JWT 密钥时自动生成随机密钥。"""

    global _settings
    if _settings is None:
        _settings = Settings()
        if not _settings.jwt_secret_key:
            # 未配置密钥时生成随机密钥，保证本地开箱即用；生产环境必须在 .env 中配置
            _settings.jwt_secret_key = secrets.token_urlsafe(48)
            logger.warning(
                "未检测到 JWT_SECRET_KEY，已生成随机临时密钥；生产环境必须在 .env 中配置固定密钥"
            )
    return _settings
