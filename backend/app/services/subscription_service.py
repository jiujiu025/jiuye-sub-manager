"""订阅生成业务逻辑：Token 解析、规则应用、缓存与日志。"""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.cache import cache_service
from app.core.exceptions import BusinessError
from app.core.security import hash_subscription_token
from app.exporters import export_nodes
from app.models.package import Package, PackageRule
from app.models.node import Node
from app.models.subscription import CustomerSubscription, SubscriptionToken, SubscriptionTokenVersion
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.package_repo import PackageRepository
from app.schemas.package import PreviewNode
from app.services.package_service import display_subscription_name
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
        # 套餐 Token 被一次性接管后，套餐原入口必须被屏蔽；否则客户订阅撤销后会从套餐入口绕过撤销。
        if self.db.scalar(select(SubscriptionToken.id).where(SubscriptionToken.token_hash == token_hash)):
            return None
        return package

    def resolve_customer_subscription(self, token: str) -> CustomerSubscription | None:
        """按独立客户订阅 Token 查找订阅；失效 Token 统一视为不存在。"""

        token_hash = hash_subscription_token(token)
        token_row = self.db.scalar(
            select(SubscriptionToken)
            .options(
                joinedload(SubscriptionToken.subscription).joinedload(CustomerSubscription.package),
                joinedload(SubscriptionToken.subscription).joinedload(CustomerSubscription.customer),
            )
            .where(SubscriptionToken.token_hash == token_hash)
        )
        if token_row is None or token_row.revoked_at is not None:
            return None
        if not hmac.compare_digest(token_row.token_hash, token_hash):
            return None
        subscription = token_row.subscription
        if subscription.status != "active" or not subscription.customer.is_active:
            return None
        return subscription

    @staticmethod
    def extract_lookup_token(value: str) -> str | None:
        """从原始 Token 或完整订阅链接中提取 Token，不记录原始输入。"""

        raw = value.strip()
        if not raw:
            return None
        if "://" in raw:
            path = unquote(urlsplit(raw).path).strip("/")
            parts = path.split("/")
            try:
                sub_index = parts.index("sub")
            except ValueError:
                return None
            return parts[sub_index + 1] if sub_index + 1 < len(parts) else None
        if raw.startswith("/sub/"):
            return raw.removeprefix("/sub/").split("/", 1)[0] or None
        return raw.split("/", 1)[0] or None

    def find_subscription_by_token(self, value: str):
        """按 Token 哈希查找客户订阅或历史套餐，供管理员找回业务记录。"""

        token = self.extract_lookup_token(value)
        if token is None:
            return None
        token_hash = hash_subscription_token(token)
        customer_token = self.db.scalar(
            select(SubscriptionToken)
            .options(
                joinedload(SubscriptionToken.subscription).joinedload(CustomerSubscription.package),
                joinedload(SubscriptionToken.subscription).joinedload(CustomerSubscription.customer),
                joinedload(SubscriptionToken.subscription).joinedload(CustomerSubscription.manager),
            )
            .where(SubscriptionToken.token_hash == token_hash)
        )
        if customer_token is not None and hmac.compare_digest(customer_token.token_hash, token_hash):
            return "customer_subscription", customer_token.subscription

        history = self.db.scalar(
            select(SubscriptionTokenVersion)
            .options(
                joinedload(SubscriptionTokenVersion.subscription).joinedload(CustomerSubscription.package),
                joinedload(SubscriptionTokenVersion.subscription).joinedload(CustomerSubscription.customer),
                joinedload(SubscriptionTokenVersion.subscription).joinedload(CustomerSubscription.manager),
            )
            .where(SubscriptionTokenVersion.token_hash == token_hash)
            .order_by(SubscriptionTokenVersion.version.desc(), SubscriptionTokenVersion.id.desc())
        )
        if history is not None:
            return "customer_subscription_history", history
        package = self.db.scalar(
            select(Package)
            .options(joinedload(Package.owner), joinedload(Package.owner_customer))
            .where(Package.token_hash == token_hash)
        )
        if package is not None and hmac.compare_digest(package.token_hash, token_hash):
            return "package", package
        return None

    @staticmethod
    def record_token_access(package: Package, client_ip: str | None) -> None:
        """记录成功解析后的 Token 访问审计，不记录 Token 明文。"""

        package.token_last_access_at = datetime.now(timezone.utc)
        package.token_last_access_ip = client_ip
        package.token_access_count = (package.token_access_count or 0) + 1

    @staticmethod
    def record_customer_token_access(
        subscription: CustomerSubscription, client_ip: str | None
    ) -> None:
        """记录客户订阅 Token 访问，不记录 Token 明文。"""

        if subscription.token is None:
            return
        subscription.token.last_access_at = datetime.now(timezone.utc)
        subscription.token.last_access_ip = client_ip
        subscription.token.access_count = (subscription.token.access_count or 0) + 1

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
    def is_expired_at(expires_at: datetime | None, now: datetime | None = None) -> bool:
        """判断一个独立订阅到期时间是否已过。"""

        if expires_at is None:
            return False
        current = now or datetime.now(timezone.utc)
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
            subscription_name=display_subscription_name(package),
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
        global_version = cache_service.version("global")
        return f"sub:{package.id}:{package.token_hash}:{output_format}:v{version}:g{global_version}"

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
    def customer_cache_key(
        subscription: CustomerSubscription, output_format: str = "clash"
    ) -> str:
        """客户订阅缓存同时隔离订阅 ID、Token 哈希和输出格式。"""

        token_hash = subscription.token.token_hash if subscription.token else "missing"
        version = cache_service.version(f"package:{subscription.package_id}:nodes")
        subscription_version = cache_service.version(f"subscription:{subscription.id}")
        global_version = cache_service.version("global")
        return (
            f"customer-sub:{subscription.id}:{token_hash}:{output_format}:"
            f"v{version}:s{subscription_version}:g{global_version}"
        )

    @staticmethod
    def get_customer_cached_entry(
        subscription: CustomerSubscription, output_format: str = "clash"
    ) -> tuple[str, int] | None:
        cached = cache_service.get(SubscriptionService.customer_cache_key(subscription, output_format))
        if cached is None:
            return None
        if isinstance(cached, tuple) and len(cached) == 2:
            return str(cached[0]), int(cached[1])
        return str(cached), 0

    @staticmethod
    def set_customer_cached(
        subscription: CustomerSubscription,
        content: str,
        output_format: str,
        node_count: int,
    ) -> None:
        cache_service.set(
            SubscriptionService.customer_cache_key(subscription, output_format),
            (content, node_count),
        )

    @staticmethod
    def invalidate_customer_subscription(subscription_id: int) -> None:
        cache_service.bump_version(f"subscription:{subscription_id}")
        cache_service.delete_prefix(f"customer-sub:{subscription_id}:")

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
