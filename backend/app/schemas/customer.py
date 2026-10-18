"""客户档案请求与响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    manager_user_id: int | None = Field(default=None, gt=0)
    region: str | None = Field(default=None, max_length=64)
    contact: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=2000)
    first_purchase_at: datetime | None = None


class CustomerAccountBind(BaseModel):
    """将已有普通用户账号绑定到客户档案。"""

    user_id: int = Field(gt=0)


class CustomerAccountCreate(BaseModel):
    """为客户直接创建普通用户登录账号。"""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    manager_user_id: int | None = Field(default=None, gt=0)
    region: str | None = Field(default=None, max_length=64)
    contact: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=2000)
    first_purchase_at: datetime | None = None
    is_active: bool | None = None


class CustomerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    manager_user_id: int | None
    manager_username: str | None
    region: str | None
    contact: str | None
    note: str | None
    first_purchase_at: datetime | None
    is_active: bool
    subscription_count: int = 0
    created_at: datetime
    updated_at: datetime
    account_user_id: int | None = None
    account_username: str | None = None
    account_is_active: bool | None = None
