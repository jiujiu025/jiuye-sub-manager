"""套餐与套餐规则模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class Package(Base):
    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    subscription_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_last_access_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_last_access_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    rules: Mapped["PackageRule"] = relationship(
        back_populates="package",
        uselist=False,
        cascade="all, delete-orphan",
    )
    owner: Mapped["User | None"] = relationship()


class PackageRule(Base):
    __tablename__ = "package_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    source_filter: Mapped[list | None] = mapped_column(JSON, nullable=True)
    node_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    country_filter: Mapped[list | None] = mapped_column(JSON, nullable=True)
    type_filter: Mapped[list | None] = mapped_column(JSON, nullable=True)
    include_keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    exclude_keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rename_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sort_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    package: Mapped[Package] = relationship(back_populates="rules")
