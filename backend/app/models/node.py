"""统一节点池模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    server: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    uuid: Mapped[str | None] = mapped_column(Text, nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    cipher: Mapped[str | None] = mapped_column(String(64), nullable=True)
    network: Mapped[str | None] = mapped_column(String(32), nullable=True)
    security: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tls: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sni: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    node_fingerprint: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
