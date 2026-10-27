"""统一节点池模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_code: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True
    )
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
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    source_type: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    source_subtype: Mapped[str | None] = mapped_column(String(32), nullable=True)
    node_category: Mapped[str] = mapped_column(
        String(16), default="external", index=True, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    node_fingerprint: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    source_node_key: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    health_status: Mapped[str] = mapped_column(
        String(16), default="unknown", index=True, nullable=False
    )
    health_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    health_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    health_tcp_status: Mapped[str] = mapped_column(
        String(16), default="unknown", nullable=False
    )
    health_tls_status: Mapped[str] = mapped_column(
        String(16), default="unknown", nullable=False
    )
    health_tcp_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_tls_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_udp_status: Mapped[str] = mapped_column(
        String(16), default="unknown", nullable=False
    )
    health_udp_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    health_success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    health_incident_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class NodeCodeSequence(Base):
    """节点业务编号序列；独立于节点表，确保删除后不会复用编号。"""

    __tablename__ = "node_code_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False)
