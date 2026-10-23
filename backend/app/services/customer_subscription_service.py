"""客户订阅业务逻辑：开通、Token rotation、吊销与审计。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import BusinessError
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    generate_subscription_token,
    hash_subscription_token,
    token_prefix,
)
from app.models.customer import Customer
from app.models.package import Package
from app.models.subscription import CustomerSubscription, SubscriptionToken, SubscriptionTokenVersion
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.repositories.user_repo import UserRepository
from app.schemas.subscription import (
    CustomerSubscriptionCreate,
    CustomerSubscriptionRenew,
    CustomerSubscriptionSummary,
    CustomerSubscriptionUpdate,
)
from app.services.manager_scope import effective_manager_id, subscription_manager_clause
from app.services.package_service import normalize_expiration, subscription_url
from app.services.notification_writer import create_admin_notifications
from app.services.subscription_state import effective_subscription_status
from app.services.customer_subscription_lines import ensure_lines


def _utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class CustomerSubscriptionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.log_repo = LogRepository(db)
        self.user_repo = UserRepository(db)

    def list(
        self,
        manager_user_id: int | None = None,
        include_company_cost: bool = True,
    ) -> list[CustomerSubscriptionSummary]:
        statement = (
            select(CustomerSubscription)
            .options(
                joinedload(CustomerSubscription.customer).joinedload(Customer.manager),
                joinedload(CustomerSubscription.package),
                joinedload(CustomerSubscription.token),
                joinedload(CustomerSubscription.manager),
            )
            .order_by(CustomerSubscription.created_at.desc(), CustomerSubscription.id.desc())
        )
        if manager_user_id is not None:
            statement = statement.join(CustomerSubscription.customer).where(
                subscription_manager_clause(manager_user_id)
            )
        rows = self.db.scalars(statement).all()
        return [self.to_summary(item, include_company_cost=include_company_cost) for item in rows]

    def get(
        self, subscription_id: int, manager_user_id: int | None = None
    ) -> CustomerSubscription | None:
        statement = (
            select(CustomerSubscription)
            .options(
                joinedload(CustomerSubscription.customer).joinedload(Customer.manager),
                joinedload(CustomerSubscription.package),
                joinedload(CustomerSubscription.token),
                joinedload(CustomerSubscription.manager),
            )
            .where(CustomerSubscription.id == subscription_id)
        )
        if manager_user_id is not None:
            statement = statement.join(CustomerSubscription.customer).where(
                subscription_manager_clause(manager_user_id)
            )
        return self.db.scalar(statement)

    def list_for_customer(self, customer_id: int) -> list[CustomerSubscription]:
        """按客户档案查询订阅，供客户门户使用。"""

        statement = (
            select(CustomerSubscription)
            .options(
                joinedload(CustomerSubscription.package),
                joinedload(CustomerSubscription.token),
            )
            .where(CustomerSubscription.customer_id == customer_id)
            .order_by(CustomerSubscription.created_at.desc(), CustomerSubscription.id.desc())
        )
        return list(self.db.scalars(statement).all())

    def get_for_customer(
        self, subscription_id: int, customer_id: int
    ) -> CustomerSubscription | None:
        """按订阅 ID 和客户 ID 双重约束，避免客户间越权读取。"""

        statement = (
            select(CustomerSubscription)
            .options(
                joinedload(CustomerSubscription.package),
                joinedload(CustomerSubscription.token),
            )
            .where(
                CustomerSubscription.id == subscription_id,
                CustomerSubscription.customer_id == customer_id,
            )
        )
        return self.db.scalar(statement)

    def create(self, payload: CustomerSubscriptionCreate, admin: User) -> tuple[CustomerSubscription, str]:
        customer = self.db.get(Customer, payload.customer_id)
        if customer is None or not customer.is_active:
            raise BusinessError("客户不存在或已停用")
        if admin.role == "manager" and customer.manager_user_id != admin.id:
            raise BusinessError("客户不属于当前经理")
        package = self.db.get(Package, payload.package_id)
        if package is None:
            raise BusinessError("套餐不存在")
        if not package.enabled:
            raise BusinessError("不能为已停用套餐开通订阅")
        # 留空表示继承客户当前经理，不能把继承关系固化成显式经理，
        # 否则客户转移后该订阅仍会被旧经理看到。
        manager_user_id = self._validate_manager(payload.manager_user_id)
        company_cost_price, sales_cost_price = self._cost_values(payload, admin)
        token, token_mode, source_package_id = self._prepare_token(payload, package)
        item = CustomerSubscription(
            customer_id=customer.id,
            package_id=package.id,
            manager_user_id=manager_user_id,
            status="active",
            started_at=_utc(payload.started_at) or datetime.now(timezone.utc),
            expires_at=normalize_expiration(payload.expires_at),
            sale_price=payload.sale_price,
            company_cost_price=company_cost_price,
            sales_cost_price=sales_cost_price,
            cost_price=company_cost_price,
            note=payload.note.strip() if payload.note else None,
        )
        customer.first_purchase_at = customer.first_purchase_at or item.started_at
        item.token = SubscriptionToken(
            token_hash=hash_subscription_token(token),
            token_prefix=token_prefix(token),
            token_encrypted=encrypt_secret(token),
            token_mode=token_mode,
            source_package_id=source_package_id,
        )
        self.db.add(item)
        self.db.flush()
        # 固化开通时的线路快照，使后续可以逐条设置到期时间。
        ensure_lines(self.db, item)
        self._record_token_version(
            item,
            token,
            action="created",
            actor=admin,
            reason="创建客户订阅",
        )
        self.log_repo.create_admin_log(admin.id, "create_customer_subscription", "subscription", customer.name)
        recipients = list(
            self.db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True))).all()
        )
        if manager_user_id is not None:
            recipients.append(manager_user_id)
        create_admin_notifications(
            self.db,
            kind="subscription_assignment",
            title="新客户订阅已分配",
            content=f"客户「{customer.name}」已开通套餐「{package.name}」。",
            dedupe_key=f"subscription-assignment:{item.id}",
            target_type="subscription",
            target_id=item.id,
            recipient_user_ids=list(set(recipients)),
        )
        self.db.commit()
        self.db.refresh(item)
        return item, token

    def update(self, item: CustomerSubscription, payload: CustomerSubscriptionUpdate, admin: User) -> CustomerSubscription:
        data = payload.model_dump(exclude_unset=True)
        legacy_cost = data.pop("cost_price", None) if "cost_price" in payload.model_fields_set else None
        company_cost = data.pop("company_cost_price", None) if "company_cost_price" in payload.model_fields_set else None
        sales_cost = data.pop("sales_cost_price", None) if "sales_cost_price" in payload.model_fields_set else None
        if admin.role == "admin":
            if "company_cost_price" in payload.model_fields_set:
                item.company_cost_price = company_cost
                item.cost_price = company_cost
            elif "cost_price" in payload.model_fields_set:
                item.company_cost_price = legacy_cost
                item.cost_price = legacy_cost
            if "sales_cost_price" in payload.model_fields_set:
                item.sales_cost_price = sales_cost
        elif "sales_cost_price" in payload.model_fields_set:
            item.sales_cost_price = sales_cost
        elif "cost_price" in payload.model_fields_set:
            item.sales_cost_price = legacy_cost
        for key, value in data.items():
            if key == "expires_at":
                value = normalize_expiration(value)
            elif key == "started_at":
                value = _utc(value)
            elif key == "note":
                # 备注允许清空，空白内容统一按 NULL 保存，避免产生无意义的空字符串。
                value = (value.strip() or None) if value else None
            elif key == "manager_user_id":
                value = self._validate_manager(value)
            setattr(item, key, value)
        self.log_repo.create_admin_log(admin.id, "update_customer_subscription", "subscription", str(item.id))
        self.db.commit()
        self.db.refresh(item)
        return item

    def regenerate_token(self, item: CustomerSubscription, admin: User) -> str:
        token = generate_subscription_token()
        now = datetime.now(timezone.utc)
        self._close_current_token_version(item, now)
        if item.token is None:
            item.token = SubscriptionToken(
                token_hash=hash_subscription_token(token),
                token_prefix=token_prefix(token),
                token_encrypted=encrypt_secret(token),
                token_mode="generated",
            )
        else:
            item.token.token_hash = hash_subscription_token(token)
            item.token.token_prefix = token_prefix(token)
            item.token.token_encrypted = encrypt_secret(token)
            item.token.token_mode = "generated"
            item.token.source_package_id = None
            item.token.created_at = now
            item.token.last_access_at = None
            item.token.last_access_ip = None
            item.token.access_count = 0
            item.token.revoked_at = None
        self.db.flush()
        self._record_token_version(
            item,
            token,
            action="regenerated",
            actor=admin,
            reason="手动重新生成 Token",
        )
        self.log_repo.create_admin_log(admin.id, "regenerate_customer_subscription_token", "subscription", str(item.id))
        recipients = list(
            self.db.scalars(
                select(User.id).where(User.role == "admin", User.is_active.is_(True))
            ).all()
        )
        manager_id = effective_manager_id(item)
        if manager_id is not None:
            recipients.append(manager_id)
        create_admin_notifications(
            self.db,
            kind="token",
            title="客户订阅 Token 已更换",
            content=f"客户「{item.customer.name}」的订阅 Token 已重新生成，旧地址已失效。",
            dedupe_key=f"subscription-token-rotation:{item.id}:{item.token.created_at.isoformat()}",
            target_type="subscription",
            target_id=item.id,
            recipient_user_ids=list(set(recipients)),
        )
        self.db.commit()
        from app.services.subscription_service import SubscriptionService

        SubscriptionService.invalidate_customer_subscription(item.id)
        return token

    def restore_token(
        self,
        item: CustomerSubscription,
        version: SubscriptionTokenVersion,
        admin: User,
        reason: str | None = None,
    ) -> str:
        """恢复历史 Token；仅管理员可调用，恢复后仍会产生新的当前版本记录。"""

        if version.subscription_id != item.id:
            raise BusinessError("Token 历史记录不属于当前订阅")
        if version.valid_to is None:
            raise BusinessError("该 Token 已经是当前版本")
        try:
            token = decrypt_secret(version.token_encrypted)
        except Exception:
            raise BusinessError("历史 Token 不可解密，无法恢复") from None
        token_hash = hash_subscription_token(token)
        if token_hash != version.token_hash:
            raise BusinessError("历史 Token 校验失败，无法恢复")
        existing = self.db.scalar(
            select(SubscriptionToken).where(
                SubscriptionToken.token_hash == token_hash,
                SubscriptionToken.subscription_id != item.id,
            )
        )
        if existing is not None:
            raise BusinessError("该 Token 已被其他客户订阅使用，不能恢复")
        package = self.db.scalar(select(Package).where(Package.token_hash == token_hash))
        if package is not None and package.id != item.package_id and package.token_revoked_at is None:
            raise BusinessError("该 Token 属于其他套餐，不能恢复")
        now = datetime.now(timezone.utc)
        self._close_current_token_version(item, now)
        if item.token is None:
            item.token = SubscriptionToken(
                token_hash=token_hash,
                token_prefix=token_prefix(token),
                token_encrypted=encrypt_secret(token),
                token_mode="restored",
                source_package_id=version.source_package_id,
            )
        else:
            item.token.token_hash = token_hash
            item.token.token_prefix = token_prefix(token)
            item.token.token_encrypted = encrypt_secret(token)
            item.token.token_mode = "restored"
            item.token.source_package_id = version.source_package_id
            item.token.created_at = now
            item.token.last_access_at = None
            item.token.last_access_ip = None
            item.token.access_count = 0
            item.token.revoked_at = None
        self.db.flush()
        self._record_token_version(
            item,
            token,
            action="restored",
            actor=admin,
            reason=reason.strip() if reason else "恢复历史 Token",
            token_mode="restored",
            source_package_id=version.source_package_id,
        )
        self.log_repo.create_admin_log(admin.id, "restore_customer_subscription_token", "subscription", str(item.id))
        self._notify_lifecycle(
            item,
            "客户订阅 Token 已恢复",
            f"客户「{item.customer.name}」的订阅已恢复历史 Token。",
            priority="high",
        )
        self.db.commit()
        from app.services.subscription_service import SubscriptionService

        SubscriptionService.invalidate_customer_subscription(item.id)
        return token

    def list_token_history(self, item: CustomerSubscription) -> list[SubscriptionTokenVersion]:
        """按时间倒序返回 Token 历史，明文只在恢复时由后端按需解密。"""

        return list(
            self.db.scalars(
                select(SubscriptionTokenVersion)
                .options(joinedload(SubscriptionTokenVersion.actor))
                .where(SubscriptionTokenVersion.subscription_id == item.id)
                .order_by(SubscriptionTokenVersion.version.desc(), SubscriptionTokenVersion.id.desc())
            ).all()
        )

    def revoke_token(self, item: CustomerSubscription, admin: User) -> None:
        if item.token is not None:
            revoked_at = datetime.now(timezone.utc)
            item.token.revoked_at = revoked_at
            self._close_current_token_version(item, revoked_at)
        self.log_repo.create_admin_log(admin.id, "revoke_customer_subscription_token", "subscription", str(item.id))
        recipients = list(
            self.db.scalars(
                select(User.id).where(User.role == "admin", User.is_active.is_(True))
            ).all()
        )
        manager_id = effective_manager_id(item)
        if manager_id is not None:
            recipients.append(manager_id)
        create_admin_notifications(
            self.db,
            kind="token",
            title="客户订阅 Token 已撤销",
            content=f"客户「{item.customer.name}」的订阅 Token 已撤销，订阅地址立即失效。",
            dedupe_key=f"subscription-token-revoke:{item.id}:{item.token.revoked_at.isoformat()}",
            priority="high",
            target_type="subscription",
            target_id=item.id,
            recipient_user_ids=list(set(recipients)),
        )
        self.db.commit()
        from app.services.subscription_service import SubscriptionService

        SubscriptionService.invalidate_customer_subscription(item.id)

    def renew(
        self,
        item: CustomerSubscription,
        payload: CustomerSubscriptionRenew,
        actor: User,
    ) -> CustomerSubscription:
        """续费并恢复可用状态；只影响当前客户订阅。"""

        if item.status == "cancelled":
            raise BusinessError("已取消的订阅不能直接续费")
        if item.token is None or item.token.revoked_at is not None:
            raise BusinessError("当前订阅 Token 已撤销，请先生成新 Token")
        if payload.days is None and payload.expires_at is None:
            raise BusinessError("请填写续费天数或新的到期时间")
        if payload.days is not None and payload.expires_at is not None:
            raise BusinessError("续费天数和到期时间只能填写一个")

        now = datetime.now(timezone.utc)
        current_expiry = _utc(item.expires_at)
        if payload.days is not None:
            base = current_expiry if current_expiry and current_expiry > now else now
            new_expiry = base + timedelta(days=payload.days)
        else:
            new_expiry = _utc(payload.expires_at)
        if new_expiry is None or new_expiry <= now:
            raise BusinessError("新的到期时间必须晚于当前时间")
        if current_expiry is not None and new_expiry <= current_expiry:
            raise BusinessError("新的到期时间必须晚于当前到期时间")

        item.expires_at = new_expiry
        item.status = "active"
        if payload.sale_price is not None:
            item.sale_price = payload.sale_price
        if actor.role == "admin":
            if payload.company_cost_price is not None:
                item.company_cost_price = payload.company_cost_price
                item.cost_price = payload.company_cost_price
            if payload.sales_cost_price is not None:
                item.sales_cost_price = payload.sales_cost_price
        elif payload.sales_cost_price is not None:
            item.sales_cost_price = payload.sales_cost_price
        if payload.note is not None:
            item.note = payload.note.strip() or None

        self.log_repo.create_admin_log(actor.id, "renew_customer_subscription", "subscription", str(item.id))
        self._notify_lifecycle(item, "客户订阅已续费", f"客户「{item.customer.name}」的订阅已续费至 {new_expiry.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC。")
        self.db.commit()
        self.db.refresh(item)
        from app.services.subscription_service import SubscriptionService

        SubscriptionService.invalidate_customer_subscription(item.id)
        return item

    def change_status(self, item: CustomerSubscription, status: str, actor: User) -> CustomerSubscription:
        """统一处理暂停、恢复和取消，避免页面直接拼接状态。"""

        if status not in {"active", "paused", "cancelled"}:
            raise BusinessError("不支持的订阅状态")
        if status == "active":
            if item.token is None or item.token.revoked_at is not None:
                raise BusinessError("当前订阅 Token 已撤销，请先生成新 Token")
            if item.expires_at is not None and _utc(item.expires_at) <= datetime.now(timezone.utc):
                raise BusinessError("订阅已到期，请先续费")
        if item.status == status:
            return item
        item.status = status
        labels = {"active": "恢复", "paused": "暂停", "cancelled": "取消"}
        self.log_repo.create_admin_log(actor.id, f"{status}_customer_subscription", "subscription", str(item.id))
        self._notify_lifecycle(
            item,
            f"客户订阅已{labels[status]}",
            f"客户「{item.customer.name}」的套餐「{item.package.name}」已{labels[status]}。",
            priority="high" if status != "active" else "normal",
        )
        self.db.commit()
        self.db.refresh(item)
        from app.services.subscription_service import SubscriptionService

        SubscriptionService.invalidate_customer_subscription(item.id)
        return item

    def _notify_lifecycle(
        self,
        item: CustomerSubscription,
        title: str,
        content: str,
        priority: str = "normal",
    ) -> None:
        """向管理员和当前有效负责人发送订阅生命周期通知。"""

        recipients = list(
            self.db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True))).all()
        )
        manager_id = effective_manager_id(item)
        if manager_id is not None:
            recipients.append(manager_id)
        create_admin_notifications(
            self.db,
            kind="subscription_lifecycle",
            title=title,
            content=content,
            dedupe_key=f"subscription-lifecycle:{item.id}:{item.status}:{datetime.now(timezone.utc).isoformat()}",
            priority=priority,
            target_type="subscription",
            target_id=item.id,
            recipient_user_ids=list(set(recipients)),
        )

    @staticmethod
    def to_summary(
        item: CustomerSubscription, *, include_company_cost: bool = True
    ) -> CustomerSubscriptionSummary:
        token = item.token
        if token is None:
            raise BusinessError("客户订阅缺少 Token")
        manager = item.manager or item.customer.manager
        return CustomerSubscriptionSummary(
            id=item.id,
            customer_id=item.customer_id,
            customer_name=item.customer.name,
            manager_user_id=effective_manager_id(item),
            manager_username=manager.username if manager else None,
            package_id=item.package_id,
            package_name=item.package.name,
            status=effective_subscription_status(item),
            started_at=_utc(item.started_at),
            expires_at=_utc(item.expires_at),
            sale_price=item.sale_price,
            company_cost_price=item.company_cost_price if include_company_cost else None,
            sales_cost_price=item.sales_cost_price,
            note=item.note,
            token_prefix=token.token_prefix,
            token_mode=token.token_mode,
            token_source_package_id=token.source_package_id,
            token_created_at=_utc(token.created_at),
            token_last_access_at=_utc(token.last_access_at),
            token_last_access_ip=token.last_access_ip,
            token_access_count=token.access_count,
            token_revoked_at=_utc(token.revoked_at),
            created_at=_utc(item.created_at),
            updated_at=_utc(item.updated_at),
        )

    @staticmethod
    def line_summaries(item: CustomerSubscription) -> list[dict]:
        """返回订阅线路摘要；调用方需先确保线路明细已加载。"""

        from app.services.customer_subscription_lines import to_summary

        return [to_summary(line) for line in item.lines]

    @staticmethod
    def subscription_url(token: str) -> str:
        return subscription_url(token)

    @staticmethod
    def subscription_url_from_item(item: CustomerSubscription) -> str:
        """从加密存储中按需解密当前订阅 Token。"""

        if item.token is None or item.token.revoked_at is not None:
            raise BusinessError("当前订阅 Token 已失效", status_code=404)
        try:
            token = decrypt_secret(item.token.token_encrypted)
        except Exception:
            raise BusinessError("当前订阅 Token 不可用", status_code=404) from None
        return subscription_url(token)

    def _validate_manager(self, manager_user_id: int | None) -> int | None:
        """只允许保存启用中的经理账号。"""

        if manager_user_id is None:
            return None
        manager = self.user_repo.get_by_id(manager_user_id)
        if manager is None or manager.role != "manager" or not manager.is_active:
            raise BusinessError("经理不存在或已停用")
        return manager.id

    def _prepare_token(self, payload: CustomerSubscriptionCreate, package: Package) -> tuple[str, str, int | None]:
        """准备客户 Token；套餐 Token 只能被一次性接管，不能并行共享。"""

        source_package_id: int | None = None
        if payload.token_mode == "generated":
            token = generate_subscription_token()
            token_mode = "generated"
        elif payload.token_mode == "package":
            if package.token_revoked_at is not None or not package.token_encrypted:
                raise BusinessError("当前套餐 Token 已撤销或不可用")
            try:
                token = decrypt_secret(package.token_encrypted)
            except Exception:
                raise BusinessError("当前套餐 Token 不可用") from None
            if hash_subscription_token(token) != package.token_hash:
                raise BusinessError("当前套餐 Token 校验失败")
            token_mode = "package"
            source_package_id = package.id
        else:
            token = (payload.custom_token or "").strip()
            if not token:
                raise BusinessError("手动 Token 不能为空")
            token_mode = "manual"

        if not re.fullmatch(r"[A-Za-z0-9._~-]{16,256}", token):
            raise BusinessError("Token 只能包含字母、数字、点、下划线、短横线和波浪线，长度为 16-256 位")
        token_hash = hash_subscription_token(token)
        if self.db.scalar(select(SubscriptionToken.id).where(SubscriptionToken.token_hash == token_hash)):
            raise BusinessError("该 Token 已被其他客户订阅使用")
        package_with_token = self.db.scalar(select(Package).where(Package.token_hash == token_hash))
        if package_with_token is not None:
            if package_with_token.id != package.id:
                raise BusinessError("该 Token 属于其他套餐，不能接管")
            if package_with_token.token_revoked_at is not None:
                raise BusinessError("该套餐 Token 已撤销，不能恢复使用")
            source_package_id = package.id
            if token_mode == "manual":
                token_mode = "package"
        return token, token_mode, source_package_id

    def _record_token_version(
        self,
        item: CustomerSubscription,
        token: str,
        *,
        action: str,
        actor: User | None,
        reason: str | None,
        token_mode: str | None = None,
        source_package_id: int | None = None,
    ) -> SubscriptionTokenVersion:
        version = int(
            self.db.scalar(
                select(func.max(SubscriptionTokenVersion.version)).where(
                    SubscriptionTokenVersion.subscription_id == item.id
                )
            )
            or 0
        ) + 1
        current = datetime.now(timezone.utc)
        row = SubscriptionTokenVersion(
            subscription_id=item.id,
            token_hash=hash_subscription_token(token),
            token_prefix=token_prefix(token),
            token_encrypted=encrypt_secret(token),
            token_mode=token_mode or item.token.token_mode,
            source_package_id=source_package_id if source_package_id is not None else item.token.source_package_id,
            version=version,
            action=action,
            actor_user_id=actor.id if actor else None,
            valid_from=current,
            reason=reason,
        )
        self.db.add(row)
        return row

    def _close_current_token_version(self, item: CustomerSubscription, ended_at: datetime) -> None:
        current = self.db.scalar(
            select(SubscriptionTokenVersion)
            .where(
                SubscriptionTokenVersion.subscription_id == item.id,
                SubscriptionTokenVersion.valid_to.is_(None),
            )
            .order_by(SubscriptionTokenVersion.version.desc())
        )
        if current is not None:
            current.valid_to = ended_at

    @staticmethod
    def _cost_values(
        payload: CustomerSubscriptionCreate, admin: User
    ) -> tuple[object | None, object | None]:
        """兼容旧 cost_price，同时按角色决定可写入的成本字段。"""

        legacy = payload.cost_price
        if admin.role == "admin":
            company = payload.company_cost_price if payload.company_cost_price is not None else legacy
            return company, payload.sales_cost_price
        sales = payload.sales_cost_price if payload.sales_cost_price is not None else legacy
        return None, sales
