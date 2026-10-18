"""站内通知模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Notification(Base):
    """面向管理员、经理或客户的站内通知，不保存订阅 Token。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_subscriptions.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", index=True, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_push_status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, index=True
    )
    telegram_push_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_delivered_chat_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    wechat_push_status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, index=True
    )
    wechat_push_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    wechat_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wechat_delivered_openids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    external_push_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    external_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
