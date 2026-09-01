"""系统设置请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SystemSettingsResponse(BaseModel):
    """可运行时修改的系统设置。"""

    sync_interval_minutes: int
    sync_enabled: bool
    cache_ttl_seconds: int
    dedup_source_priority: list[str]


class SystemSettingsUpdate(BaseModel):
    sync_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    sync_enabled: bool | None = None
    cache_ttl_seconds: int | None = Field(default=None, ge=30, le=86400)
    dedup_source_priority: list[str] | None = None
