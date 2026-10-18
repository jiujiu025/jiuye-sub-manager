"""客户订阅请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CustomerSubscriptionCreate(BaseModel):
    customer_id: int = Field(gt=0)
    package_id: int = Field(gt=0)
    manager_user_id: int | None = Field(default=None, gt=0)
    started_at: datetime | None = None
    expires_at: datetime | None = None
    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    company_cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sales_cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2, exclude=True)
    note: str | None = Field(default=None, max_length=2000)
    token_mode: Literal["generated", "package", "manual"] = "generated"
    custom_token: str | None = Field(default=None, min_length=16, max_length=256)


class CustomerSubscriptionUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|paused|cancelled)$")
    manager_user_id: int | None = Field(default=None, gt=0)
    started_at: datetime | None = None
    expires_at: datetime | None = None
    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    company_cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sales_cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2, exclude=True)
    note: str | None = Field(default=None, max_length=2000)


class CustomerSubscriptionRenew(BaseModel):
    """续费参数；按天续费或指定新的到期时间，二选一。"""

    days: int | None = Field(default=None, gt=0, le=3650)
    expires_at: datetime | None = None
    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sales_cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    company_cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=2000)


class CustomerSubscriptionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    customer_name: str
    manager_user_id: int | None
    manager_username: str | None
    package_id: int
    package_name: str
    status: str
    started_at: datetime
    expires_at: datetime | None
    sale_price: Decimal | None
    company_cost_price: Decimal | None
    sales_cost_price: Decimal | None
    note: str | None
    token_prefix: str
    token_mode: str
    token_source_package_id: int | None
    token_created_at: datetime
    token_last_access_at: datetime | None
    token_last_access_ip: str | None
    token_access_count: int
    token_revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CustomerSubscriptionCreateResponse(CustomerSubscriptionSummary):
    """创建或 rotation 时一次性返回明文 Token。"""

    token: str
    subscription_url: str


class CustomerSubscriptionUrlResponse(BaseModel):
    subscription_id: int
    subscription_url: str


class SubscriptionTokenVersionSummary(BaseModel):
    """Token 历史摘要，不返回明文 Token。"""

    id: int
    subscription_id: int
    token_prefix: str
    token_mode: str
    source_package_id: int | None
    version: int
    action: str
    actor_user_id: int | None
    actor_username: str | None
    valid_from: datetime
    valid_to: datetime | None
    reason: str | None
    created_at: datetime


class RestoreSubscriptionTokenRequest(BaseModel):
    version_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=255)


class SubscriptionLookupRequest(BaseModel):
    """管理员查找订阅时提交的 Token 或完整订阅链接。"""

    query: str = Field(min_length=1, max_length=4096)


class SubscriptionLookupResponse(BaseModel):
    """订阅查找结果；只返回 Token 前缀，不返回明文 Token。"""

    kind: Literal["customer_subscription", "package"]
    id: int
    package_name: str
    customer_name: str | None = None
    manager_username: str | None = None
    status: str
    expires_at: datetime | None = None
    note: str | None = None
    token_prefix: str
    historical: bool = False
    history_id: int | None = None
    token_revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CustomerPortalProfile(BaseModel):
    """客户门户资料；未绑定客户时只返回 bound=false。"""

    bound: bool
    customer_id: int | None = None
    name: str | None = None
    region: str | None = None
    manager_username: str | None = None


class CustomerPortalSubscription(BaseModel):
    """客户门户订阅摘要，不包含销售价或任何成本字段。"""

    id: int
    package_id: int
    package_name: str
    status: str
    started_at: datetime
    expires_at: datetime | None
    token_prefix: str
    token_created_at: datetime
    token_revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime
