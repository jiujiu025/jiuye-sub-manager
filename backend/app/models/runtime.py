"""多进程运行时协调数据模型。"""

from __future__ import annotations

from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RateLimitEvent(Base):
    """共享限流窗口中的请求占用记录。"""

    __tablename__ = "rate_limit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rate_key: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (Index("ix_rate_limit_events_key_time", "rate_key", "occurred_at"),)


class CacheNamespaceVersion(Base):
    """共享缓存命名空间版本；缓存正文仍保留在各 worker 内存中。"""

    __tablename__ = "cache_namespace_versions"

    namespace: Mapped[str] = mapped_column(String(255), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class SchedulerLease(Base):
    """定时任务租约，保证多 worker 只有一个实例执行同一任务。"""

    __tablename__ = "scheduler_leases"

    job_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_until: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
