"""上游订阅业务逻辑。"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.models.source import Source
from app.models.package import PackageRule
from app.models.three_xui import ForwardTask, ForwardedNodeMapping
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.source_repo import SourceRepository
from app.schemas.source import SourceCreate, SourceUpdate
from app.services.subscription_service import SubscriptionService


def normalize_source_expiration(value: datetime | None) -> datetime | None:
    """把资源到期时间统一保存为 UTC。"""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def validate_source_url(url: str) -> None:
    """校验上游订阅 URL，并拒绝明显的本机/内网目标。"""

    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise BusinessError("订阅 URL 地址或端口无效") from exc
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise BusinessError("订阅 URL 必须是有效的 http/https 地址")
    if parsed.username or parsed.password:
        raise BusinessError("订阅 URL 不允许携带用户信息")
    if not hostname or hostname in {"localhost", "localhost.localdomain"}:
        raise BusinessError("订阅 URL 不允许指向本机地址")
    if port is not None and not 0 < port < 65536:
        raise BusinessError("订阅 URL 端口无效")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise BusinessError("订阅 URL 不允许指向内网或保留地址")


class SourceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SourceRepository(db)
        self.node_repo = NodeRepository(db)
        self.log_repo = LogRepository(db)

    def create(self, payload: SourceCreate, admin: User) -> Source:
        validate_source_url(payload.url)
        if self.repo.get_by_name(payload.name) is not None:
            raise BusinessError("订阅名称已存在")
        source = self.repo.create(
            name=payload.name,
            url=payload.url,
            enabled=payload.enabled,
            allow_empty_override=payload.allow_empty_override,
            fmt=payload.format,
            expires_at=normalize_source_expiration(payload.expires_at),
        )
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="create_source",
            target_type="source",
            target_value=source.name,
        )
        self.db.commit()
        self.db.refresh(source)
        return source

    def update(self, source: Source, payload: SourceUpdate, admin: User) -> Source:
        data = payload.model_dump(exclude_unset=True)
        affected_package_ids: set[int] = set()
        source_node_ids = {node.id for node in self.node_repo.list_by_source(source.id)}
        for key in ("name", "url"):
            if key in data and data[key] is None:
                raise BusinessError(f"订阅字段 {key} 不能为 null")
        if "url" in data:
            validate_source_url(data["url"])
            if data["url"] != source.url:
                source.etag = None
                source.last_modified = None
        if "format" in data and data["format"] != source.format:
            source.etag = None
            source.last_modified = None
        if "expires_at" in data:
            data["expires_at"] = normalize_source_expiration(data["expires_at"])
            affected_package_ids = SubscriptionService.affected_package_ids_for_source(
                self.db, source.name, source_node_ids, source_node_ids
            )
        if "name" in data and data["name"] != source.name:
            if self.repo.get_by_name(data["name"]) is not None:
                raise BusinessError("订阅名称已存在")
            old_name = source.name
            new_name = data["name"]
            old_node_ids = {node.id for node in self.node_repo.list_by_source(source.id)}
            affected_package_ids = SubscriptionService.affected_package_ids_for_source(
                self.db, old_name, old_node_ids, old_node_ids
            )
            for node in self.node_repo.list_by_source(source.id):
                node.source_name = new_name
            for rule in self.db.scalars(select(PackageRule)).all():
                if isinstance(rule.source_filter, list):
                    rule.source_filter = [
                        new_name if value == old_name else value
                        for value in rule.source_filter
                    ]
        for key, value in data.items():
            setattr(source, key, value)
        if "expires_at" in data:
            for node in self.node_repo.list_by_source(source.id):
                node.expires_at = data["expires_at"]
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="update_source",
            target_type="source",
            target_value=source.name,
        )
        self.db.commit()
        self.db.refresh(source)
        for package_id in affected_package_ids:
            SubscriptionService.invalidate_package(package_id)
        return source

    def delete(self, source: Source, admin: User) -> None:
        old_node_ids = {node.id for node in self.node_repo.list_by_source(source.id)}
        if old_node_ids:
            mapping_exists = self.db.scalar(
                select(ForwardedNodeMapping.id)
                .where(ForwardedNodeMapping.source_node_id.in_(old_node_ids))
                .limit(1)
            )
            if mapping_exists is not None:
                raise BusinessError(
                    "该订阅源仍有 3x-ui 转发映射，请先解除转发映射后再删除",
                    status_code=409,
                )
            active_task_exists = self.db.scalar(
                select(ForwardTask.id)
                .where(
                    ForwardTask.source_node_id.in_(old_node_ids),
                    ForwardTask.status.in_(("pending", "running", "succeeded")),
                )
                .limit(1)
            )
            if active_task_exists is not None:
                raise BusinessError(
                    "该订阅源仍有待处理或已完成的 3x-ui 转发任务，请先处理后再删除",
                    status_code=409,
                )
            # 失败任务没有有效映射时仅作为执行记录，删除源节点前清理其外键引用。
            self.db.execute(
                delete(ForwardTask).where(
                    ForwardTask.source_node_id.in_(old_node_ids),
                    ForwardTask.status == "failed",
                )
            )
        affected_package_ids = SubscriptionService.affected_package_ids_for_source(
            self.db, source.name, old_node_ids, set()
        )
        self.node_repo.delete_by_source(source.id)
        for rule in self.db.scalars(select(PackageRule)).all():
            # 删除来源后保留原筛选值，使套餐变为无匹配，而不是误变成全来源。
            # 空列表在套餐规则中代表“不限制来源”，不能用它表示来源已删除。
            if isinstance(rule.node_ids, list) and old_node_ids:
                rule.node_ids = [
                    value for value in rule.node_ids
                    if str(value).isdigit() and int(value) not in old_node_ids
                ]
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="delete_source",
            target_type="source",
            target_value=source.name,
        )
        self.repo.delete(source)
        self.db.commit()
        for package_id in affected_package_ids:
            SubscriptionService.invalidate_package(package_id)
