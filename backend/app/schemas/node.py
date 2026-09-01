"""节点池相关响应模型。"""

from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.core.security import mask_secret
from app.schemas.common import ORMModel


class NodeSummary(ORMModel):
    """节点池列表响应：敏感凭证脱敏。"""

    id: int
    source_id: int | None
    source_name: str
    original_name: str
    name: str
    type: str
    server: str
    port: int
    network: str | None
    security: str | None
    country: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
    uuid: str | None = Field(default=None, exclude=True)
    password: str | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def uuid_masked(self) -> str | None:
        return mask_secret(self.uuid) if self.uuid else None

    @computed_field
    @property
    def password_masked(self) -> str | None:
        return mask_secret(self.password) if self.password else None


class NodeCreate(BaseModel):
    """自有节点创建请求。"""

    name: str = Field(min_length=1, max_length=255)
    type: Literal["vless", "shadowsocks"] = "vless"
    server: str = Field(min_length=1, max_length=255)
    port: int = Field(gt=0, lt=65536)
    uuid: str | None = None
    password: str | None = None
    cipher: str | None = None
    network: str | None = None
    security: str | None = None
    tls: bool | None = None
    sni: str | None = None
    fingerprint: str | None = None
    public_key: str | None = None
    short_id: str | None = None
    path: str | None = None
    host: str | None = None
    country: str | None = None
    enabled: bool = True


class NodeUpdate(BaseModel):
    """自有节点更新请求。"""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    server: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, gt=0, lt=65536)
    uuid: str | None = None
    password: str | None = None
    cipher: str | None = None
    network: str | None = None
    security: str | None = None
    tls: bool | None = None
    sni: str | None = None
    fingerprint: str | None = None
    public_key: str | None = None
    short_id: str | None = None
    path: str | None = None
    host: str | None = None
    country: str | None = None
    enabled: bool | None = None


class NodeBatchRequest(BaseModel):
    """节点批量操作请求。"""

    ids: list[int] = Field(min_length=1)
    action: Literal["enable", "disable", "delete"]


class NodeDetail(ORMModel):
    """节点详情：仅认证管理员可见完整敏感字段。"""

    id: int
    source_id: int | None
    source_name: str
    original_name: str
    name: str
    type: str
    server: str
    port: int
    uuid: str | None
    password: str | None
    cipher: str | None
    network: str | None
    security: str | None
    tls: bool | None
    sni: str | None
    fingerprint: str | None
    public_key: str | None
    short_id: str | None
    path: str | None
    host: str | None
    country: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
