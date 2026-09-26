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
    username: str | None = Field(default=None, exclude=True)
    source_type: str | None
    source_subtype: str | None

    @computed_field
    @property
    def uuid_masked(self) -> str | None:
        return mask_secret(self.uuid) if self.uuid else None

    @computed_field
    @property
    def password_masked(self) -> str | None:
        return mask_secret(self.password) if self.password else None

    @computed_field
    @property
    def username_masked(self) -> str | None:
        return mask_secret(self.username) if self.username else None


class NodeCreate(BaseModel):
    """自有节点创建请求。"""

    name: str = Field(min_length=1, max_length=255)
    type: Literal[
        "vless",
        "vmess",
        "shadowsocks",
        "trojan",
        "socks",
        "http",
        "hysteria",
        "hysteria2",
        "tuic",
        "anytls",
    ] = "vless"
    server: str = Field(min_length=1, max_length=255)
    port: int = Field(gt=0, lt=65536)
    uuid: str | None = None
    password: str | None = None
    username: str | None = None
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
    source_subtype: Literal["custom_url", "custom_manual", "custom_import"] = (
        "custom_manual"
    )


class NodeUpdate(BaseModel):
    """自有节点更新请求。"""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    server: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, gt=0, lt=65536)
    uuid: str | None = None
    password: str | None = None
    username: str | None = None
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
    source_subtype: Literal["custom_url", "custom_manual", "custom_import"] | None = None


class NodeBatchRequest(BaseModel):
    """节点批量操作请求。"""

    ids: list[int] = Field(min_length=1)
    action: Literal["enable", "disable", "delete"]


class NodeImportRequest(BaseModel):
    """自有节点批量导入请求。"""

    content: str = Field(min_length=1, max_length=2_000_000)
    source_subtype: Literal["custom_url", "custom_import"] = "custom_url"
    format: str = "auto"


class ImportFailure(BaseModel):
    index: int
    reason: str


class NodeImportResult(BaseModel):
    """导入统计：成功/重复/失败，失败原因不包含完整敏感链接。"""

    total: int
    success: int
    duplicate: int
    failed: int
    failures: list[ImportFailure]


class NodeExportResponse(BaseModel):
    """单节点分享链接响应。"""

    node_id: int
    name: str
    type: str
    format: str
    content: str


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
    username: str | None
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
    source_type: str | None
    source_subtype: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
