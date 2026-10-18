"""经理工作台响应模型。"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class RegionCount(BaseModel):
    region: str
    customer_count: int


class ManagerStats(BaseModel):
    customer_count: int
    active_subscription_count: int
    expiring_subscription_count: int
    sales_total: Decimal
    regions: list[RegionCount]
