"""概览统计响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DashboardStats(BaseModel):
    source_count: int
    enabled_source_count: int
    node_count: int
    self_node_count: int
    package_count: int
    enabled_package_count: int
    failed_source_count: int
    last_sync_at: datetime | None
