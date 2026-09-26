"""上游订阅相关请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.core.security import mask_secret
from app.schemas.common import ORMModel

SourceFormat = Literal[
    "auto", "clash", "singbox", "v2ray-json", "v2ray", "base64", "vless", "vmess", "ss", "trojan"
]


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=8, max_length=2048)
    enabled: bool = True
    allow_empty_override: bool = False
    format: SourceFormat = "auto"


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    url: str | None = Field(default=None, min_length=8, max_length=2048)
    enabled: bool | None = None
    allow_empty_override: bool | None = None
    format: SourceFormat | None = None


class SourceSummary(ORMModel):
    """列表响应：URL 脱敏展示。"""

    id: int
    name: str
    url: str = Field(exclude=True)
    enabled: bool
    allow_empty_override: bool
    format: str
    node_count: int
    version: int
    last_sync_status: str
    last_sync_at: datetime | None
    last_error: str | None
    last_success_at: datetime | None
    last_success_node_count: int | None
    last_sync_duration_ms: int | None
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def url_masked(self) -> str:
        return mask_secret(self.url, keep_head=16, keep_tail=10)


class SourceDetail(ORMModel):
    """详情响应：仅认证管理员可见完整 URL。"""

    id: int
    name: str
    url: str
    enabled: bool
    allow_empty_override: bool
    format: str
    node_count: int
    version: int
    last_sync_status: str
    last_sync_at: datetime | None
    last_error: str | None
    last_success_at: datetime | None
    last_success_node_count: int | None
    last_sync_duration_ms: int | None
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime


class SyncResult(BaseModel):
    source_id: int
    source_name: str
    status: str
    node_count: int
    added_count: int
    removed_count: int
    changed_count: int
    version: int
    error: str | None = None
