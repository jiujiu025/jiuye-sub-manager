"""套餐业务逻辑：规则筛选、重命名、排序、Token 生命周期。"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

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
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.package_repo import PackageRepository
from app.repositories.user_repo import UserRepository
from app.schemas.package import (
    PackageCreate,
    PackageDetail,
    PackageRulesPayload,
    PackageUpdate,
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

    def delete(self, package: Package, admin: User) -> None:
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

        rules = package.rules
        source_filter = rules.source_filter if rules else None
        node_ids = rules.node_ids if rules else None
        country_filter = rules.country_filter if rules else None
        type_filter = rules.type_filter if rules else None
        include_keywords = rules.include_keywords if rules else None
        exclude_keywords = rules.exclude_keywords if rules else None

        nodes = self.node_repo.list_enabled_with_filters(
            sources=source_filter or None,
            node_ids=node_ids or None,
            countries=country_filter or None,
            types=type_filter or None,
            include_keywords=include_keywords or None,
            exclude_keywords=exclude_keywords or None,
        )
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
        rename_rules = rules.rename_rules if rules else []
        for preview in previews:
            preview.name = apply_rename_rules(preview.name, rename_rules or [])
        apply_sort_rules(previews, (rules.sort_rules or []) if rules else [])
        apply_numbering(previews, rename_rules or [])
        return previews

    def to_detail(self, package: Package) -> PackageDetail:
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

    def _validate_owner(self, owner_user_id: int | None) -> None:
        """确保套餐只能归属给存在且可登录的普通用户。"""

        if owner_user_id is None:
            return
        owner = self.user_repo.get_by_id(owner_user_id)
        if owner is None or owner.role != "user":
            raise BusinessError("归属用户不存在或不是普通用户")
        if not owner.is_active:
            raise BusinessError("不能把套餐分配给已禁用用户")

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
