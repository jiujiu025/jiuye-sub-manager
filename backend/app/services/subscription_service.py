"""订阅生成业务逻辑：Token 解析、规则应用、缓存与日志。"""

from __future__ import annotations

import hmac
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import cache_service
from app.core.exceptions import BusinessError
from app.core.security import hash_subscription_token
from app.exporters import export_nodes
from app.models.package import Package, PackageRule
from app.models.node import Node
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

        token_hash = hash_subscription_token(token)
        package = self.package_repo.get_by_token_hash(token_hash)
        if package is None or package.token_revoked_at is not None or not hmac.compare_digest(
            package.token_hash, token_hash
        ):
            return None
        return package

    @staticmethod
    def record_token_access(package: Package, client_ip: str | None) -> None:
        """记录成功解析后的 Token 访问审计，不记录 Token 明文。"""

        package.token_last_access_at = datetime.now(timezone.utc)
        package.token_last_access_ip = client_ip
        package.token_access_count = (package.token_access_count or 0) + 1

    @staticmethod
    def is_expired(package: Package, now: datetime | None = None) -> bool:
        """判断套餐是否已到期；空到期时间表示长期有效。"""

        if package.expires_at is None:
            return False
        current = now or datetime.now(timezone.utc)
        expires_at = package.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= current

    @staticmethod
    def generate_expired(output_format: str) -> tuple[str, int]:
        """生成唯一不可连接的到期提示节点，避免客户端继续使用旧节点。"""

        name = "订阅已到期，请续费使用"
        node = Node(
            source_name="系统提示",
            original_name=name,
            name=name,
            type="vless",
            server="127.0.0.1",
            port=1,
            uuid="00000000-0000-4000-8000-000000000000",
            network="tcp",
            tls=False,
            enabled=True,
            node_fingerprint="expired-subscription",
        )
        return export_nodes([(node, name)], output_format, subscription_name=name)

    def generate(self, package: Package, output_format: str = "clash") -> tuple[str, int]:
        """应用套餐规则并按客户端格式生成订阅，不触发上游同步。"""

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
        content, node_count = export_nodes(
            items,
            output_format,
            subscription_name=package.subscription_name or package.name,
        )
        if node_count == 0:
            raise BusinessError("套餐暂无可用节点", status_code=404)
        return content, node_count

    def generate_clash(self, package: Package) -> tuple[str, int]:
        """兼容现有调用方，生成默认 Clash YAML。"""

        return self.generate(package, "clash")

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
    def cache_key(package: Package, output_format: str = "clash") -> str:
        version = cache_service.version(f"package:{package.id}:nodes")
        return f"sub:{package.id}:{package.token_hash}:{output_format}:v{version}"

    @staticmethod
    def get_cached(package: Package, output_format: str = "clash") -> str | None:
        """读取缓存内容，兼容旧版仅保存字符串的缓存值。"""

        cached = cache_service.get(SubscriptionService.cache_key(package, output_format))
        if isinstance(cached, tuple):
            return cached[0]
        return cached

    @staticmethod
    def get_cached_entry(
        package: Package, output_format: str = "clash"
    ) -> tuple[str, int] | None:
        """读取订阅内容及缓存时生成的节点数。"""

        cached = cache_service.get(SubscriptionService.cache_key(package, output_format))
        if cached is None:
            return None
        if isinstance(cached, tuple) and len(cached) == 2:
            return str(cached[0]), int(cached[1])
        return str(cached), 0

    @staticmethod
    def set_cached(
        package: Package,
        content: str,
        output_format: str = "clash",
        node_count: int = 0,
    ) -> None:
        """缓存订阅内容及其实际导出节点数。"""

        cache_service.set(
            SubscriptionService.cache_key(package, output_format),
            (content, node_count),
        )

    @staticmethod
    def invalidate_package(package_id: int) -> None:
        """精确失效单个套餐的所有格式缓存。"""

        cache_service.bump_version(f"package:{package_id}:nodes")
        cache_service.delete_prefix(f"sub:{package_id}:")

    @staticmethod
    def invalidate_for_source(
        db: Session,
        source_name: str,
        old_node_ids: set[int],
        new_node_ids: set[int],
    ) -> None:
        """只失效可能受来源节点变化影响的套餐缓存。"""

        for package_id in SubscriptionService.affected_package_ids_for_source(
            db, source_name, old_node_ids, new_node_ids
        ):
            SubscriptionService.invalidate_package(package_id)

    @staticmethod
    def affected_package_ids_for_source(
        db: Session,
        source_name: str,
        old_node_ids: set[int],
        new_node_ids: set[int],
    ) -> set[int]:
        """查找受来源节点变化影响的套餐，供事务提交后执行缓存失效。"""

        changed_ids = old_node_ids | new_node_ids
        rows = db.execute(
            select(Package.id, PackageRule.source_filter, PackageRule.node_ids)
            .select_from(Package)
            .outerjoin(PackageRule, PackageRule.package_id == Package.id)
        ).all()
        package_ids: set[int] = set()
        for package_id, source_filter, node_ids in rows:
            selected_sources = set(source_filter or []) if isinstance(source_filter, list) else set()
            selected_ids = {
                int(value)
                for value in (node_ids or [])
                if isinstance(value, int) or str(value).isdigit()
            }
            impacted = (
                source_name in selected_sources
                or bool(selected_ids & changed_ids)
                or (not selected_sources and not selected_ids)
            )
            if impacted:
                package_ids.add(package_id)
        return package_ids
