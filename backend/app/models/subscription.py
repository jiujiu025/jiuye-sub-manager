"""客户订阅和独立订阅 Token 模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class CustomerSubscription(Base):
    """客户购买记录，引用现有套餐作为节点规则方案。"""

    __tablename__ = "customer_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    manager_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="active", index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    company_cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    sales_cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # 保留旧列，兼容已有数据库和历史代码；新业务统一使用上面的两个字段。
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    customer: Mapped["Customer"] = relationship(back_populates="subscriptions")
    package: Mapped["Package"] = relationship()
    manager: Mapped["User | None"] = relationship()
    token: Mapped["SubscriptionToken | None"] = relationship(
        back_populates="subscription", uselist=False, cascade="all, delete-orphan"
    )


class SubscriptionToken(Base):
    """客户订阅的 Bearer Token，只保存哈希和加密密文。"""

    __tablename__ = "subscription_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("customer_subscriptions.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    token_mode: Mapped[str] = mapped_column(String(16), default="generated", nullable=False)
    source_package_id: Mapped[int | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_access_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_access_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subscription: Mapped[CustomerSubscription] = relationship(back_populates="token")


class SubscriptionTokenVersion(Base):
    """客户订阅 Token 的不可变版本记录，不直接向普通列表暴露明文。"""

    __tablename__ = "subscription_token_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("customer_subscriptions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    token_mode: Mapped[str] = mapped_column(String(16), default="generated", nullable=False)
    source_package_id: Mapped[int | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL"), index=True, nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    subscription: Mapped[CustomerSubscription] = relationship()
    actor: Mapped["User | None"] = relationship()
