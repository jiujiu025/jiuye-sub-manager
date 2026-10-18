"""系统设置请求/响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SystemSettingsResponse(BaseModel):
    """可运行时修改的系统设置。"""

    sync_interval_minutes: int
    sync_enabled: bool
    cache_ttl_seconds: int
    dedup_source_priority: list[str]
    health_enabled: bool
    health_interval_minutes: int
    health_timeout_seconds: float
    health_failure_threshold: int
    health_recovery_threshold: int
    health_probe_concurrency: int
    health_probe_mode: Literal["full", "basic"]
    telegram_enabled: bool
    telegram_configured: bool
    telegram_chat_ids_masked: list[str]
    wechat_enabled: bool
    wechat_configured: bool
    wechat_openids_masked: list[str]


class SystemSettingsUpdate(BaseModel):
    sync_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    sync_enabled: bool | None = None
    cache_ttl_seconds: int | None = Field(default=None, ge=30, le=86400)
    dedup_source_priority: list[str] | None = None
    health_enabled: bool | None = None
    health_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    health_timeout_seconds: float | None = Field(default=None, ge=1, le=60)
    health_failure_threshold: int | None = Field(default=None, ge=1, le=10)
    health_recovery_threshold: int | None = Field(default=None, ge=1, le=10)
    health_probe_concurrency: int | None = Field(default=None, ge=1, le=100)
    health_probe_mode: Literal["full", "basic"] | None = None
    telegram_enabled: bool | None = None
    telegram_bot_token: str | None = Field(default=None, max_length=512)
    telegram_chat_ids: list[str] | None = Field(default=None, max_length=50)
    clear_telegram_config: bool = False
    wechat_enabled: bool | None = None
    wechat_app_id: str | None = Field(default=None, max_length=128)
    wechat_app_secret: str | None = Field(default=None, max_length=512)
    wechat_template_id: str | None = Field(default=None, max_length=256)
    wechat_openids: list[str] | None = Field(default=None, max_length=100)
    clear_wechat_config: bool = False


class NotificationTestRequest(BaseModel):
    """外部通知测试请求。"""

    channel: Literal["telegram", "wechat"]
    content: str = Field(default="这是一条 Sub-Manager 测试通知。", min_length=1, max_length=500)
