"""同步日志、订阅请求日志、管理员操作日志模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    removed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )


class SubscriptionLog(Base):
    __tablename__ = "subscription_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
