"""应用配置：统一从环境变量和 .env 文件读取。"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

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
    app_env: str = "development"
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
    upstream_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
    cors_origins: str = "*"
    public_base_url: str = "http://localhost:8000"
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128,172.16.0.0/12"
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 60
    subscription_rate_limit: int = 120
    subscription_rate_window_seconds: int = 60


_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置单例；生产环境缺少关键配置时拒绝启动。"""

    global _settings
    if _settings is None:
        settings = Settings()
        if settings.app_env.strip().lower() in {"production", "prod"}:
            if len(settings.jwt_secret_key) < 32:
                raise RuntimeError("生产环境 JWT_SECRET_KEY 长度至少为 32 个字符")
            if settings.jwt_algorithm not in {"HS256", "HS384", "HS512"}:
                raise RuntimeError("生产环境 JWT_ALGORITHM 不受支持")
            missing = [
                name
                for name, value in (
                    ("JWT_SECRET_KEY", settings.jwt_secret_key),
                    ("ADMIN_PASSWORD", settings.admin_password),
                    ("PUBLIC_BASE_URL", settings.public_base_url),
                )
                if not value or not value.strip()
            ]
            if missing:
                raise RuntimeError("生产环境必须配置：" + ", ".join(missing))
            parsed_url = urlparse(settings.public_base_url)
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                raise RuntimeError("生产环境 PUBLIC_BASE_URL 必须是有效的 HTTPS 地址")
            if not settings.cors_origins.strip() or settings.cors_origins.strip() == "*":
                settings.cors_origins = f"{parsed_url.scheme}://{parsed_url.netloc}"
                logger.warning(
                    "生产环境未配置明确的 CORS_ORIGINS，已收紧为 PUBLIC_BASE_URL 的来源"
                )
        _settings = settings
        if not settings.jwt_secret_key:
            # 未配置密钥时生成随机密钥，保证本地开箱即用；生产环境必须在 .env 中配置
            settings.jwt_secret_key = secrets.token_urlsafe(48)
            logger.warning(
                "未检测到 JWT_SECRET_KEY，已生成随机临时密钥；生产环境必须在 .env 中配置固定密钥"
            )
    return _settings
