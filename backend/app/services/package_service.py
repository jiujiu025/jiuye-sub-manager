"""套餐业务逻辑：规则筛选、重命名、排序、Token 生命周期。"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.cache import cache_service
from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    generate_subscription_token,
    hash_subscription_token,
    token_prefix,
)
from app.models.base import utcnow
from app.models.package import Package, PackageRule
from app.models.customer import Customer
from app.models.node import Node
from app.models.subscription import CustomerSubscription
from app.models.subscription import SubscriptionToken
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.package_repo import PackageRepository
from app.repositories.user_repo import UserRepository
from app.services.notification_writer import create_admin_notifications
from app.services.manager_scope import effective_manager_id
from app.services.subscription_state import is_effectively_active
from app.schemas.package import (
    PackageCreate,
    PackageDuplicateRequest,
    PackageDetail,
    PackageRulesPayload,
    PackageUpdate,
    PackageCustomerUsage,
    PreviewNode,
)
from app.utils.node_rules import (
    apply_numbering,
    apply_rename_rules,
    apply_sort_rules,
)


def subscription_url(token: str) -> str:
    """根据公开基础地址拼接订阅 URL。"""

    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/sub/{token}"


def subscription_url_for_package(package: Package) -> str | None:
    """解密套餐 Token 并返回订阅地址；旧数据或密钥变化时返回 None。"""

    if not package.token_encrypted:
        return None
    try:
        token = decrypt_secret(package.token_encrypted)
    except Exception:
        return None
    return subscription_url(token)


def display_subscription_name(package: Package) -> str:
    """订阅显示名称：未设置时回退到套餐名称。"""

    return normalize_subscription_name(package.subscription_name) or package.name


def normalize_subscription_name(value: str | None) -> str | None:
    """归一化订阅显示名称：strip 后为空视为未设置。"""

    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def normalize_token_name(value: str | None) -> str | None:
    """归一化 Token 后台显示名称。"""

    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class PackageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PackageRepository(db)
        self.node_repo = NodeRepository(db)
        self.log_repo = LogRepository(db)
        self.user_repo = UserRepository(db)

    def create(self, payload: PackageCreate, admin: User) -> tuple[Package, str]:
        """创建套餐并生成一次性明文 Token。"""

        if self.repo.get_by_name(payload.name) is not None:
            raise BusinessError("套餐名称已存在")
        self._validate_owner(payload.owner_user_id)
        self._validate_owner_customer(payload.owner_customer_id)
        token = generate_subscription_token()
        package = self.repo.create(
            name=payload.name,
            subscription_name=(
                normalize_subscription_name(payload.subscription_name) or payload.name
            ),
            enabled=payload.enabled,
            description=payload.description,
            expires_at=normalize_expiration(payload.expires_at),
            token_hash=hash_subscription_token(token),
            token_prefix=token_prefix(token),
            token_encrypted=encrypt_secret(token),
            owner_user_id=payload.owner_user_id,
            owner_customer_id=payload.owner_customer_id,
            token_name=normalize_token_name(payload.token_name) or payload.name,
        )
        package.token_created_at = utcnow()
        rule = self._build_rule(package, payload.rules)
        self.db.add(rule)
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="create_package",
            target_type="package",
            target_value=package.name,
        )
        self.db.commit()
        self.db.refresh(package)
        cache_service.invalidate_all()
        return package, token

    def update(
        self, package: Package, payload: PackageUpdate, admin: User
    ) -> Package:
        """修改套餐基本信息与规则。"""

        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is None:
            raise BusinessError("套餐名称不能为 null")
        rules_payload = data.pop("rules", None)
        if "name" in data and data["name"] != package.name:
            if self.repo.get_by_name(data["name"]) is not None:
                raise BusinessError("套餐名称已存在")
        if "owner_user_id" in data:
            self._validate_owner(data["owner_user_id"])
        if "owner_customer_id" in data:
            self._validate_owner_customer(data["owner_customer_id"])
        for key, value in data.items():
            if key == "subscription_name":
                setattr(package, key, normalize_subscription_name(value))
                continue
            if key == "expires_at":
                setattr(package, key, normalize_expiration(value))
                continue
            if key == "token_name":
                setattr(package, key, normalize_token_name(value))
                continue
            setattr(package, key, value)
        if rules_payload is not None:
            self._update_rules(package, PackageRulesPayload(**rules_payload))
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="update_package",
            target_type="package",
            target_value=package.name,
        )
        self.db.commit()
        self.db.refresh(package)
        cache_service.invalidate_all()
        return package

    def duplicate(
        self,
        package: Package,
        payload: PackageDuplicateRequest,
        admin: User,
    ) -> tuple[Package, str]:
        """复制套餐规则并创建全新的、默认停用的 Token。"""

        if self.repo.get_by_name(payload.name) is not None:
            raise BusinessError("套餐名称已存在")

        token = generate_subscription_token()
        duplicate = self.repo.create(
            name=payload.name,
            subscription_name=(
                normalize_subscription_name(payload.subscription_name)
                or payload.name
            ),
            enabled=payload.enabled,
            description=payload.description,
            expires_at=normalize_expiration(payload.expires_at),
            token_hash=hash_subscription_token(token),
            token_prefix=token_prefix(token),
            token_encrypted=encrypt_secret(token),
            owner_user_id=None,
            owner_customer_id=None,
            token_name=payload.name,
        )
        duplicate.token_created_at = utcnow()

        source_rules = package.rules
        rules_payload = PackageRulesPayload.model_validate(
            {
                "source_filter": (source_rules.source_filter or []) if source_rules else [],
                "node_ids": (source_rules.node_ids or []) if source_rules else [],
                "country_filter": (source_rules.country_filter or []) if source_rules else [],
                "type_filter": (source_rules.type_filter or []) if source_rules else [],
                "include_keywords": (source_rules.include_keywords or []) if source_rules else [],
                "exclude_keywords": (source_rules.exclude_keywords or []) if source_rules else [],
                "rename_rules": (source_rules.rename_rules or []) if source_rules else [],
                "sort_rules": (source_rules.sort_rules or []) if source_rules else [],
            }
        )
        self.db.add(self._build_rule(duplicate, rules_payload))
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="duplicate_package",
            target_type="package",
            target_value=f"{package.name} -> {duplicate.name}",
        )
        self.db.commit()
        self.db.refresh(duplicate)
        cache_service.invalidate_all()
        return duplicate, token

    def delete(self, package: Package, admin: User) -> None:
        linked_subscription = self.db.scalar(
            select(CustomerSubscription.id)
            .where(CustomerSubscription.package_id == package.id)
            .limit(1)
        )
        if linked_subscription is not None:
            raise BusinessError("套餐已有客户订阅，不能删除；请先停用套餐或处理客户订阅")
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="delete_package",
            target_type="package",
            target_value=package.name,
        )
        self.repo.delete(package)
        self.db.commit()
        cache_service.invalidate_all()

    def regenerate_token(self, package: Package, admin: User) -> str:
        """重生成 Token，旧 Token 因哈希被覆盖而立即失效。"""

        token = generate_subscription_token()
        package.token_hash = hash_subscription_token(token)
        package.token_prefix = token_prefix(token)
        package.token_encrypted = encrypt_secret(token)
        package.token_name = package.token_name or package.name
        package.token_created_at = utcnow()
        package.token_last_access_at = None
        package.token_last_access_ip = None
        package.token_access_count = 0
        package.token_revoked_at = None
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="regenerate_token",
            target_type="package",
            target_value=package.name,
        )
        create_admin_notifications(
            self.db,
            kind="token",
            title="套餐 Token 已更换",
            content=f"套餐「{package.name}」的订阅 Token 已重新生成，旧地址已失效。",
            dedupe_key=f"package-token-rotation:{package.id}:{package.token_created_at.isoformat()}",
            target_type="package",
            target_id=package.id,
        )
        self.db.commit()
        cache_service.invalidate_all()
        return token

    def revoke_token(self, package: Package, admin: User) -> None:
        """吊销当前 Token，不生成新 Token；后续可通过 rotation 恢复访问。"""

        package.token_hash = hash_subscription_token(secrets.token_urlsafe(32))
        package.token_prefix = "revoked"
        package.token_encrypted = None
        package.token_revoked_at = utcnow()
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="revoke_token",
            target_type="package",
            target_value=package.name,
        )
        create_admin_notifications(
            self.db,
            kind="token",
            title="套餐 Token 已撤销",
            content=f"套餐「{package.name}」的订阅 Token 已撤销，订阅地址立即失效。",
            dedupe_key=f"package-token-revoke:{package.id}:{package.token_revoked_at.isoformat()}",
            priority="high",
            target_type="package",
            target_id=package.id,
        )
        self.db.commit()
        cache_service.invalidate_all()

    def rename_token(self, package: Package, token_name: str, admin: User) -> Package:
        """修改 Token 的后台显示名称，不改变 Token 本身。"""

        normalized = normalize_token_name(token_name)
        if not normalized:
            raise BusinessError("Token 名称不能为空")
        package.token_name = normalized
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="rename_token",
            target_type="package",
            target_value=package.name,
        )
        self.db.commit()
        self.db.refresh(package)
        return package

    def toggle(self, package: Package, admin: User) -> Package:
        """启用/禁用套餐。"""

        package.enabled = not package.enabled
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="toggle_package",
            target_type="package",
            target_value=package.name,
        )
        self.db.commit()
        self.db.refresh(package)
        cache_service.invalidate_all()
        return package

    def preview(self, package: Package) -> list[PreviewNode]:
        """动态应用套餐规则，返回筛选/重命名/排序后的节点。"""

        nodes = self.node_repo.list_enabled_with_filters(
            sources=(package.rules.source_filter or []) if package.rules else None,
            node_ids=(package.rules.node_ids or []) if package.rules else None,
            countries=(package.rules.country_filter or []) if package.rules else None,
            types=(package.rules.type_filter or []) if package.rules else None,
            include_keywords=(package.rules.include_keywords or []) if package.rules else None,
            exclude_keywords=(package.rules.exclude_keywords or []) if package.rules else None,
        )
        return self.preview_from_nodes(package, nodes)

    @staticmethod
    def preview_from_nodes(package: Package, nodes: list[Node]) -> list[PreviewNode]:
        """在已有节点集合上应用套餐规则，供批量线路查询复用。"""

        rules = package.rules
        source_filter = set(rules.source_filter or []) if rules else set()
        node_ids = {
            int(value)
            for value in (rules.node_ids or [] if rules else [])
            if isinstance(value, int) or str(value).isdigit()
        }
        country_filter = set(rules.country_filter or []) if rules else set()
        type_filter = set(rules.type_filter or []) if rules else set()
        include_keywords = [
            str(value).strip().lower()
            for value in (rules.include_keywords or [] if rules else [])
            if str(value).strip()
        ]
        exclude_keywords = [
            str(value).strip().lower()
            for value in (rules.exclude_keywords or [] if rules else [])
            if str(value).strip()
        ]

        filtered = []
        for node in nodes:
            # source_filter 和 node_ids 是“任一匹配”，与 NodeRepository 保持一致。
            if (source_filter or node_ids) and not (
                node.source_name in source_filter or node.id in node_ids
            ):
                continue
            if country_filter and node.country not in country_filter:
                continue
            if type_filter and node.type not in type_filter:
                continue
            lowered_name = node.name.lower()
            if include_keywords and not any(keyword in lowered_name for keyword in include_keywords):
                continue
            if exclude_keywords and any(keyword in lowered_name for keyword in exclude_keywords):
                continue
            filtered.append(node)

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
            for node in filtered
        ]
        rename_rules = rules.rename_rules if rules else []
        for preview in previews:
            preview.name = apply_rename_rules(preview.name, rename_rules or [])
        apply_sort_rules(previews, (rules.sort_rules or []) if rules else [])
        apply_numbering(previews, rename_rules or [])
        return previews

    def to_details(
        self, packages: list[Package], viewer_manager_id: int | None = None
    ) -> list[PackageDetail]:
        """批量转换套餐详情，避免套餐列表逐条查询客户使用关系。"""

        usage = self._customer_usage(
            [package.id for package in packages], viewer_manager_id
        )
        return [
            self.to_detail(
                package,
                usage.get(package.id, []),
                viewer_manager_id=viewer_manager_id,
            )
            for package in packages
        ]

    def to_detail(
        self,
        package: Package,
        used_by_customers: list[PackageCustomerUsage] | None = None,
        viewer_manager_id: int | None = None,
    ) -> PackageDetail:
        """把套餐与规则 ORM 转换为 API 响应。"""

        rules = package.rules
        return PackageDetail(
            id=package.id,
            name=package.name,
            subscription_name=display_subscription_name(package),
            enabled=package.enabled,
            description=package.description,
            token_prefix=package.token_prefix,
            token_name=package.token_name or package.name,
            token_created_at=package.token_created_at or package.created_at,
            token_last_access_at=package.token_last_access_at,
            token_last_access_ip=package.token_last_access_ip,
            token_access_count=package.token_access_count,
            token_revoked_at=package.token_revoked_at,
            subscription_url=None,
            owner_user_id=package.owner_user_id,
            owner_username=package.owner.username if package.owner else None,
            owner_customer_id=(
                package.owner_customer_id
                if viewer_manager_id is None
                or package.owner_customer is None
                or package.owner_customer.manager_user_id == viewer_manager_id
                else None
            ),
            owner_customer_name=(
                package.owner_customer.name
                if package.owner_customer is not None
                and (
                    viewer_manager_id is None
                    or package.owner_customer.manager_user_id == viewer_manager_id
                )
                else None
            ),
            used_by_customers=(
                used_by_customers
                if used_by_customers is not None
                else self._customer_usage([package.id], viewer_manager_id).get(
                    package.id, []
                )
            ),
            expires_at=expiration_for_response(package.expires_at),
            created_at=package.created_at,
            updated_at=package.updated_at,
            rules=PackageRulesPayload(
                source_filter=(rules.source_filter or []) if rules else [],
                node_ids=(rules.node_ids or []) if rules else [],
                country_filter=(rules.country_filter or []) if rules else [],
                type_filter=(rules.type_filter or []) if rules else [],
                include_keywords=(rules.include_keywords or []) if rules else [],
                exclude_keywords=(rules.exclude_keywords or []) if rules else [],
                rename_rules=(rules.rename_rules or []) if rules else [],
                sort_rules=(rules.sort_rules or []) if rules else [],
            ),
        )

    @staticmethod
    def subscription_url(package: Package) -> str | None:
        """按需解密当前 Token；列表和详情不自动暴露该值。"""

        return subscription_url_for_package(package)

    def lookup_by_subscription(self, value: str):
        """按完整订阅链接、Token 或 Token 前缀查找套餐摘要。

        完整 Token 仍然使用哈希精确匹配；只有不少于四位的前缀才允许模糊匹配，
        避免过短输入返回大量无关结果。响应只包含 Token 前缀，不解密或回显明文 Token。
        """

        from app.schemas.package import PackageLookupItem
        from app.services.subscription_service import SubscriptionService

        token = SubscriptionService.extract_lookup_token(value)
        if not token:
            return []

        exact = SubscriptionService(self.db).find_subscription_by_token(value)
        if exact is not None:
            kind, item = exact
            if kind == "package":
                return [self._lookup_item(item, PackageLookupItem, "package")]
            is_history = kind.endswith("history")
            subscription = item.subscription if is_history else item
            return [
                self._lookup_item(
                    subscription.package,
                    PackageLookupItem,
                    "customer_subscription_history" if is_history else "customer_subscription",
                    customer_id=subscription.customer_id,
                    customer_name=subscription.customer.name,
                    manager_username=(
                        subscription.manager.username if subscription.manager else None
                    ),
                    subscription_id=subscription.id,
                    token_prefix=(item.token_prefix if is_history else subscription.token.token_prefix),
                    expires_at=subscription.expires_at,
                    status="历史 Token" if is_history else self._subscription_status(subscription),
                    created_at=item.created_at if is_history else subscription.created_at,
                    updated_at=subscription.updated_at,
                )
            ]

        if len(token) < 4 or len(token) > 8:
            return []

        package_candidates = list(
            self.db.scalars(
                select(Package)
                .options(joinedload(Package.owner_customer))
                .where(Package.token_prefix.like(f"{token}%"))
                .order_by(Package.created_at.desc())
            ).all()
        )
        results = [
            self._lookup_item(package, PackageLookupItem, "package_prefix")
            for package in package_candidates
            if package.token_prefix.startswith(token)
        ]

        customer_tokens = list(
            self.db.scalars(
                select(SubscriptionToken)
                .options(
                    joinedload(SubscriptionToken.subscription)
                    .joinedload(CustomerSubscription.package)
                    .joinedload(Package.owner_customer),
                    joinedload(SubscriptionToken.subscription).joinedload(CustomerSubscription.customer),
                    joinedload(SubscriptionToken.subscription).joinedload(CustomerSubscription.manager),
                )
                .where(SubscriptionToken.token_prefix.like(f"{token}%"))
                .order_by(SubscriptionToken.created_at.desc())
            ).all()
        )
        results.extend(
            self._lookup_item(
                item.subscription.package,
                PackageLookupItem,
                "customer_subscription_prefix",
                customer_id=item.subscription.customer_id,
                customer_name=item.subscription.customer.name,
                manager_username=(
                    item.subscription.manager.username if item.subscription.manager else None
                ),
                subscription_id=item.subscription.id,
                token_prefix=item.token_prefix,
                expires_at=item.subscription.expires_at,
                status=self._subscription_status(item.subscription),
                updated_at=item.subscription.updated_at,
            )
            for item in customer_tokens
            if item.token_prefix.startswith(token)
        )
        return results

    @staticmethod
    def _subscription_status(subscription: CustomerSubscription) -> str:
        """返回查找结果使用的客户订阅状态。"""

        if subscription.token is not None and subscription.token.revoked_at is not None:
            return "已撤销"
        if subscription.status == "cancelled":
            return "已取消"
        if subscription.status == "paused":
            return "已暂停"
        expires_at = expiration_for_response(subscription.expires_at)
        if expires_at is not None and expires_at <= utcnow():
            return "已到期"
        return "生效中"

    @staticmethod
    def _lookup_item(
        package: Package,
        schema,
        match_kind: str,
        *,
        customer_id: int | None = None,
        customer_name: str | None = None,
        manager_username: str | None = None,
        subscription_id: int | None = None,
        token_prefix: str | None = None,
        status: str | None = None,
        expires_at=None,
        created_at=None,
        updated_at=None,
    ):
        """将套餐或客户订阅匹配结果转换为不含明文 Token 的摘要。"""

        package_expires_at = expiration_for_response(package.expires_at)
        if status is None:
            if package.token_revoked_at is not None:
                status = "已撤销"
            elif not package.enabled:
                status = "已停用"
            elif package_expires_at is not None and package_expires_at <= utcnow():
                status = "已到期"
            else:
                status = "生效中"
        return schema(
            package_id=package.id,
            package_name=package.name,
            subscription_name=display_subscription_name(package),
            customer_id=customer_id,
            customer_name=customer_name,
            manager_username=manager_username,
            subscription_id=subscription_id,
            match_kind=match_kind,
            token_prefix=token_prefix or package.token_prefix,
            status=status,
            expires_at=(
                expiration_for_response(expires_at)
                if expires_at is not None
                else package_expires_at
            ),
            created_at=created_at or package.created_at,
            updated_at=updated_at or package.updated_at,
        )

    def _validate_owner(self, owner_user_id: int | None) -> None:
        """确保套餐只能归属给存在且可登录的普通用户。"""

        if owner_user_id is None:
            return
        owner = self.user_repo.get_by_id(owner_user_id)
        if owner is None or owner.role != "user":
            raise BusinessError("归属用户不存在或不是普通用户")
        if not owner.is_active:
            raise BusinessError("不能把套餐分配给已禁用用户")

    def _validate_owner_customer(self, customer_id: int | None) -> None:
        """确保套餐业务归属只指向仍可用的客户档案。"""

        if customer_id is None:
            return
        customer = self.db.get(Customer, customer_id)
        if customer is None or not customer.is_active:
            raise BusinessError("归属客户不存在或已停用")

    def _customer_usage(
        self, package_ids: list[int], viewer_manager_id: int | None = None
    ) -> dict[int, list[PackageCustomerUsage]]:
        if not package_ids:
            return {}
        rows = self.db.scalars(
            select(CustomerSubscription)
            .options(
                joinedload(CustomerSubscription.customer).joinedload(Customer.manager),
                joinedload(CustomerSubscription.manager),
            )
            .where(CustomerSubscription.package_id.in_(package_ids))
        ).all()
        grouped: dict[int, dict[int, PackageCustomerUsage]] = {}
        for row in rows:
            customer = row.customer
            if viewer_manager_id is not None and effective_manager_id(row) != viewer_manager_id:
                continue
            per_package = grouped.setdefault(row.package_id, {})
            usage = per_package.get(customer.id)
            if usage is None:
                usage = PackageCustomerUsage(
                    customer_id=customer.id,
                    customer_name=customer.name,
                    manager_username=(
                        row.manager.username
                        if row.manager is not None
                        else customer.manager.username
                        if customer.manager is not None
                        else None
                    ),
                )
                per_package[customer.id] = usage
            usage.subscription_count += 1
            if is_effectively_active(row):
                usage.active_subscription_count += 1
        return {
            package_id: sorted(items.values(), key=lambda item: (item.customer_name, item.customer_id))
            for package_id, items in grouped.items()
        }

    @staticmethod
    def _build_rule(package: Package, payload: PackageRulesPayload) -> PackageRule:
        values = payload.model_dump()
        return PackageRule(package=package, **values)

    def _update_rules(
        self, package: Package, payload: PackageRulesPayload
    ) -> None:
        values = payload.model_dump()
        if package.rules is None:
            self.db.add(self._build_rule(package, payload))
            return
        for key, value in values.items():
            setattr(package.rules, key, value or None)


def normalize_expiration(value: datetime | None) -> datetime | None:
    """把套餐到期时间统一保存为 UTC，避免服务器时区导致提前或延后失效。"""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def expiration_for_response(value: datetime | None) -> datetime | None:
    """确保 API 输出的到期时间带 UTC 标记，兼容 SQLite 丢失时区信息。"""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
