"""日志数据访问。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.log import AdminLog, SubscriptionLog, SyncLog


class LogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_admin_log(
        self,
        admin_user_id: int | None,
        action: str,
        target_type: str | None = None,
        target_value: str | None = None,
        detail: str | None = None,
    ) -> AdminLog:
        log = AdminLog(
            admin_user_id=admin_user_id,
            action=action,
            target_type=target_type,
            target_value=target_value,
            detail=detail,
        )
        self.db.add(log)
        return log

    def create_sync_log(
        self,
        source_id: int | None,
        version: int,
        status: str,
        node_count: int,
        added_count: int = 0,
        removed_count: int = 0,
        changed_count: int = 0,
        error_message: str | None = None,
    ) -> SyncLog:
        log = SyncLog(
            source_id=source_id,
            version=version,
            status=status,
            node_count=node_count,
            added_count=added_count,
            removed_count=removed_count,
            changed_count=changed_count,
            error_message=error_message,
        )
        self.db.add(log)
        return log

    def create_subscription_log(
        self,
        package_id: int | None,
        status: str,
        node_count: int,
        client_ip: str | None,
    ) -> SubscriptionLog:
        log = SubscriptionLog(
            package_id=package_id,
            status=status,
            node_count=node_count,
            client_ip=client_ip,
        )
        self.db.add(log)
        return log

    def list_sync_logs(
        self, page: int = 1, page_size: int = 50
    ) -> tuple[list[SyncLog], int]:
        base = select(SyncLog).order_by(SyncLog.created_at.desc(), SyncLog.id.desc())
        total = self.db.scalar(select(func.count()).select_from(SyncLog)) or 0
        rows = self.db.scalars(
            base.offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), total

    def list_subscription_logs(
        self, page: int = 1, page_size: int = 50
    ) -> tuple[list[SubscriptionLog], int]:
        base = select(SubscriptionLog).order_by(
            SubscriptionLog.created_at.desc(), SubscriptionLog.id.desc()
        )
        total = self.db.scalar(
            select(func.count()).select_from(SubscriptionLog)
        ) or 0
        rows = self.db.scalars(
            base.offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), total

    def list_admin_logs(
        self, page: int = 1, page_size: int = 50
    ) -> tuple[list[AdminLog], int]:
        base = select(AdminLog).order_by(
            AdminLog.created_at.desc(), AdminLog.id.desc()
        )
        total = self.db.scalar(select(func.count()).select_from(AdminLog)) or 0
        rows = self.db.scalars(
            base.offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), total
