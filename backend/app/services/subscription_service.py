"""订阅生成业务逻辑：Token 解析、规则应用、缓存与日志。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.cache import cache_service
from app.core.exceptions import BusinessError
from app.core.security import hash_subscription_token
from app.exporters.clash import ClashExporter
from app.models.package import Package
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.package_repo import PackageRepository
from app.schemas.package import PreviewNode
from app.utils.node_rules import (
    apply_numbering,
    apply_rename_rules,
    apply_sort_rules,
)


class SubscriptionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.package_repo = PackageRepository(db)
        self.node_repo = NodeRepository(db)
        self.log_repo = LogRepository(db)

    def resolve_package(self, token: str) -> Package | None:
        """按 Token 哈希查找套餐，数据库不保存明文 Token。"""

        return self.package_repo.get_by_token_hash(hash_subscription_token(token))

    def generate_clash(self, package: Package) -> tuple[str, int]:
        """应用套餐规则并生成 Clash/Mihomo YAML，不触发上游同步。"""

        rules = package.rules
        nodes = self.node_repo.list_enabled_with_filters(
            sources=(rules.source_filter or None) if rules else None,
            node_ids=(rules.node_ids or None) if rules else None,
            countries=(rules.country_filter or None) if rules else None,
            types=(rules.type_filter or None) if rules else None,
            include_keywords=(rules.include_keywords or None) if rules else None,
            exclude_keywords=(rules.exclude_keywords or None) if rules else None,
        )
        if not nodes:
            raise BusinessError("套餐暂无可用节点", status_code=404)

        rename_rules = rules.rename_rules if rules else []
        previews = [
            PreviewNode(
                id=node.id,
                source_name=node.source_name,
                original_name=node.original_name,
                name=node.name,
                type=node.type,
                server=node.server,
                port=node.port,
                country=node.country,
            )
            for node in nodes
        ]
        for preview in previews:
            preview.name = apply_rename_rules(preview.name, rename_rules or [])
        apply_sort_rules(previews, (rules.sort_rules or []) if rules else [])
        apply_numbering(previews, rename_rules or [])

        node_by_id = {node.id: node for node in nodes}
        items = [
            (node_by_id[preview.id], preview.name)
            for preview in previews
            if preview.id in node_by_id
        ]
        yaml_text = ClashExporter().export(
            items, subscription_name=package.subscription_name or package.name
        )
        return yaml_text, len(items)

    def log_subscription(
        self,
        package_id: int | None,
        status: str,
        node_count: int,
        client_ip: str | None,
    ) -> None:
        """记录订阅请求日志；Token 本身不写入日志。"""

        self.log_repo.create_subscription_log(
            package_id=package_id,
            status=status,
            node_count=node_count,
            client_ip=client_ip,
        )
        self.db.commit()

    @staticmethod
    def cache_key(package_id: int) -> str:
        return f"sub:{package_id}"

    @staticmethod
    def get_cached(package_id: int) -> str | None:
        return cache_service.get(SubscriptionService.cache_key(package_id))

    @staticmethod
    def set_cached(package_id: int, content: str) -> None:
        cache_service.set(SubscriptionService.cache_key(package_id), content)
