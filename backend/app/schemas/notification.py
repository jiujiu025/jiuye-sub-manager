"""站内通知响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscription_id: int | None
    kind: str
    priority: str
    title: str
    content: str
    read_at: datetime | None
    archived_at: datetime | None
    target_type: str | None
    target_id: int | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationSummary]
    unread_count: int
    total: int
    page: int
    page_size: int
    pages: int
