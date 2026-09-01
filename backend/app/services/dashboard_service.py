"""概览统计业务逻辑。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.package import Package
from app.models.source import Source
from app.schemas.dashboard import DashboardStats
from app.utils.priority import SELF_SOURCE_NAME


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def stats(self) -> DashboardStats:
        """统计后台首页所需的关键指标。"""

        source_count = self.db.scalar(select(func.count()).select_from(Source)) or 0
        enabled_source_count = (
            self.db.scalar(
                select(func.count())
                .select_from(Source)
                .where(Source.enabled.is_(True))
            )
            or 0
        )
        node_count = self.db.scalar(select(func.count()).select_from(Node)) or 0
        self_node_count = (
            self.db.scalar(
                select(func.count())
                .select_from(Node)
                .where(Node.source_name == SELF_SOURCE_NAME)
            )
            or 0
        )
        package_count = self.db.scalar(
            select(func.count()).select_from(Package)
        ) or 0
        enabled_package_count = (
            self.db.scalar(
                select(func.count())
                .select_from(Package)
                .where(Package.enabled.is_(True))
            )
            or 0
        )
        failed_source_count = (
            self.db.scalar(
                select(func.count())
                .select_from(Source)
                .where(Source.last_sync_status == "failed")
            )
            or 0
        )
        last_sync_at = self.db.scalar(select(func.max(Source.last_sync_at)))
        return DashboardStats(
            source_count=source_count,
            enabled_source_count=enabled_source_count,
            node_count=node_count,
            self_node_count=self_node_count,
            package_count=package_count,
            enabled_package_count=enabled_package_count,
            failed_source_count=failed_source_count,
            last_sync_at=last_sync_at,
        )
