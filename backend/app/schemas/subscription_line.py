"""客户线路列表与 Excel 导出模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SubscriptionLineSummary(BaseModel):
    """线路列表摘要；不在普通列表中返回完整线路凭据。"""

    line_key: str
    line_code: str
    subscription_id: int
    customer_id: int
    customer_name: str
    customer_region: str | None
    customer_note: str | None
    package_name: str
    manager_username: str | None
    node_id: int
    node_code: str | None
    node_name: str
    node_type: str
    node_country: str | None
    source_server: str | None
    forwarded: bool
    forwarded_server: str
    started_at: datetime
    node_created_at: datetime
    expires_at: datetime | None
    status: str


class CustomerSubscriptionLineSummary(BaseModel):
    """客户订阅线路的独立到期信息。"""

    id: int
    subscription_id: int
    node_id: int | None
    position: int
    remark: str
    expires_at: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime


class CustomerSubscriptionLineUpdate(BaseModel):
    """修改单条线路到期时间；传 null 表示长期有效。"""

    expires_at: datetime | None = None


class SubscriptionLinePage(BaseModel):
    items: list[SubscriptionLineSummary]
    total: int
    page: int
    page_size: int
    pages: int


class SubscriptionLineExportRequest(BaseModel):
    """线路导出筛选条件；line_keys 不为空时只导出选中线路。"""

    line_keys: list[str] = Field(default_factory=list, max_length=1000)
    keyword: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=16)
