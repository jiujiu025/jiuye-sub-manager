"""3x-ui 服务器和异步转发接口模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ForwardTemplate = Literal[
    "vless_tcp",
    "vless_ws_tls",
    "vmess_ws_tls",
    "trojan_tcp_tls",
    "shadowsocks_tcp",
]
ForwardMode = Literal["port_forward", "inbound_outbound"]


class ThreeXUIServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    ip: str | None = Field(default=None, max_length=128)
    domain: str | None = Field(default=None, max_length=255)
    api_url: str = Field(min_length=8, max_length=512)
    api_token: str = Field(min_length=8, max_length=512)
    version: str = Field(default="3.8.5", min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def require_address(self):
        if not (self.ip or self.domain):
            raise ValueError("服务器 IP 或域名至少填写一个")
        return self


class ThreeXUIServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    ip: str | None = Field(default=None, max_length=128)
    domain: str | None = Field(default=None, max_length=255)
    api_url: str | None = Field(default=None, min_length=8, max_length=512)
    api_token: str | None = Field(default=None, min_length=8, max_length=512)
    version: str | None = Field(default=None, min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = None
    enabled: bool | None = None


class ThreeXUIServerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ip: str | None
    domain: str | None
    api_url: str
    api_token_prefix: str
    version: str
    note: str | None
    expires_at: datetime | None
    enabled: bool
    last_api_check_at: datetime | None
    last_api_status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ThreeXUIServerCheckResponse(BaseModel):
    server_id: int
    status: Literal["healthy", "failed", "unknown"]
    checked_at: datetime
    message: str
    inbound_count: int | None = None


class ThreeXUIInboundTestCreate(BaseModel):
    template: ForwardTemplate = "vless_tcp"
    port: int | None = Field(default=None, gt=0, lt=65536)
    remark: str | None = Field(default=None, max_length=255)


class ThreeXUIInboundTestResponse(BaseModel):
    server_id: int
    inbound_id: int
    template: str
    protocol: str
    port: int
    remark: str
    message: str


class ForwardTaskCreate(BaseModel):
    source_node_id: int = Field(gt=0)
    target_server_id: int = Field(gt=0)
    template: ForwardTemplate = "vless_tcp"
    forward_mode: ForwardMode = "inbound_outbound"
    inbound_remark: str | None = Field(default=None, max_length=255)
    listen_port: int | None = Field(default=None, gt=0, lt=65536)


class ForwardBatchCreate(BaseModel):
    source_node_ids: list[int] = Field(min_length=1, max_length=100)
    target_server_id: int = Field(gt=0)
    template: ForwardTemplate = "vless_tcp"
    forward_mode: ForwardMode = "inbound_outbound"
    inbound_remark: str | None = Field(default=None, max_length=255)
    listen_port_start: int = Field(default=12900, gt=0, lt=65536)
    listen_port_end: int = Field(default=20000, gt=0, lt=65536)

    @model_validator(mode="after")
    def validate_port_range(self):
        if self.listen_port_end < self.listen_port_start:
            raise ValueError("端口范围无效")
        if len(set(self.source_node_ids)) > self.listen_port_end - self.listen_port_start + 1:
            raise ValueError("端口范围不足以处理所选节点")
        return self


class ForwardBatchSkipped(BaseModel):
    source_node_id: int
    reason: str


class ForwardTaskSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_node_id: int
    target_server_id: int
    template: str
    forward_mode: str
    inbound_remark: str | None
    listen_port: int
    auto_port: bool
    status: str
    progress: int
    stage: str
    error_message: str | None
    result_node_id: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ForwardBatchResponse(BaseModel):
    tasks: list[ForwardTaskSummary]
    skipped: list[ForwardBatchSkipped]


class ForwardedNodeMappingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_node_id: int
    forwarded_node_id: int
    target_server_id: int
    inbound_id: int
    client_id_masked: str | None
    inbound_remark: str
    template: str
    forward_mode: str
    status: str
    last_synced_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
