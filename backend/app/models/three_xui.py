"""3x-ui 服务器、异步转发任务和节点映射模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class ThreeXUIServer(Base):
    """用于执行转发的 3x-ui 服务器信息；API Token 只保存加密密文。"""

    __tablename__ = "three_xui_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(128), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="3.8.5", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True, index=True, nullable=False)
    last_api_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_api_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ForwardTask(Base):
    """3x-ui 转发异步任务。"""

    __tablename__ = "forward_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    target_server_id: Mapped[int] = mapped_column(
        ForeignKey("three_xui_servers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    template: Mapped[str] = mapped_column(String(32), nullable=False)
    forward_mode: Mapped[str] = mapped_column(
        String(24), default="inbound_outbound", nullable=False
    )
    inbound_remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    listen_port: Mapped[int] = mapped_column(Integer, nullable=False)
    auto_port: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), default="等待后台处理", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ForwardedNodeMapping(Base):
    """源节点、目标面板入站与本地 forwarded 节点的可追溯映射。"""

    __tablename__ = "forwarded_node_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    forwarded_node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    target_server_id: Mapped[int] = mapped_column(
        ForeignKey("three_xui_servers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    inbound_id: Mapped[int] = mapped_column(Integer, nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inbound_remark: Mapped[str] = mapped_column(String(255), nullable=False)
    template: Mapped[str] = mapped_column(String(32), nullable=False)
    forward_mode: Mapped[str] = mapped_column(
        String(24), default="inbound_outbound", nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="active", index=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "source_node_id",
            "target_server_id",
            "template",
            "forward_mode",
            name="uq_forwarded_mapping_source_target_template",
        ),
    )

    @property
    def client_id_masked(self) -> str | None:
        """返回脱敏后的 3x-ui 客户端标识，避免接口暴露完整凭据。"""

        if not self.client_id:
            return None
        if len(self.client_id) <= 8:
            return "***"
        return f"{self.client_id[:4]}...{self.client_id[-4:]}"
