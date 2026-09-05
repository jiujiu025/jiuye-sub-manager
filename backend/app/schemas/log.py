"""日志查询响应模型。"""

from __future__ import annotations

from datetime import datetime

from app.schemas.common import ORMModel


class SyncLogResponse(ORMModel):
    id: int
    source_id: int | None
    version: int
    status: str
    node_count: int
    added_count: int
    removed_count: int
    changed_count: int
    error_message: str | None
    created_at: datetime


class SubscriptionLogResponse(ORMModel):
    id: int
    package_id: int | None
    status: str
    node_count: int
    client_ip: str | None
    created_at: datetime


class AdminLogResponse(ORMModel):
    id: int
    admin_user_id: int | None
    action: str
    target_type: str | None
    target_value: str | None
    detail: str | None
    created_at: datetime
