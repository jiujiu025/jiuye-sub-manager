"""客户档案业务逻辑。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import hash_password
from app.models.customer import Customer
from app.models.subscription import CustomerSubscription
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.repositories.user_repo import UserRepository
from app.schemas.customer import CustomerCreate, CustomerSummary, CustomerUpdate
from app.services.notification_writer import create_admin_notifications


def _normalize_datetime(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class CustomerService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.log_repo = LogRepository(db)
        self.user_repo = UserRepository(db)

    def list(self, manager_user_id: int | None = None) -> list[CustomerSummary]:
        statement = (
            select(Customer, func.count(CustomerSubscription.id))
            .outerjoin(CustomerSubscription, CustomerSubscription.customer_id == Customer.id)
            .group_by(Customer.id)
            .order_by(Customer.created_at.desc(), Customer.id.desc())
        )
        if manager_user_id is not None:
            statement = statement.where(Customer.manager_user_id == manager_user_id)
        rows = self.db.execute(statement).all()
        return [self.to_summary(customer, count) for customer, count in rows]

    def create(self, payload: CustomerCreate, admin: User) -> Customer:
        name = payload.name.strip()
        if not name:
            raise BusinessError("客户名称不能为空")
        customer = Customer(
            name=name,
            manager_user_id=self._validate_manager(payload.manager_user_id),
            region=self._clean(payload.region),
            contact=self._clean(payload.contact),
            note=self._clean(payload.note),
            first_purchase_at=_normalize_datetime(payload.first_purchase_at),
        )
        self.db.add(customer)
        self.db.flush()
        self.log_repo.create_admin_log(admin.id, "create_customer", "customer", name)
        recipients = list(
            self.db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True))).all()
        )
        if customer.manager_user_id is not None:
            recipients.append(customer.manager_user_id)
        create_admin_notifications(
            self.db,
            kind="customer_assignment",
            title="新客户已分配",
            content=f"客户「{customer.name}」已创建并分配到销售经理。",
            dedupe_key=f"customer-assignment:{customer.id}:{customer.manager_user_id}",
            target_type="customer",
            target_id=customer.id,
            recipient_user_ids=list(set(recipients)),
        )
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def update(self, customer: Customer, payload: CustomerUpdate, admin: User) -> Customer:
        data = payload.model_dump(exclude_unset=True)
        previous_manager_id = customer.manager_user_id
        if "name" in data:
            if data["name"] is None or not data["name"].strip():
                raise BusinessError("客户名称不能为空")
            customer.name = data["name"].strip()
        if "manager_user_id" in data:
            customer.manager_user_id = self._validate_manager(data["manager_user_id"])
        manager_changed = "manager_user_id" in data and customer.manager_user_id != previous_manager_id
        if manager_changed and previous_manager_id is not None:
            # 经理销售产生的订阅会记录显式负责人。客户转移时同步迁移原负责人名下的订阅，
            # 避免旧经理继续看到客户的订阅；其他显式负责人不被误改。
            self.db.execute(
                update(CustomerSubscription)
                .where(
                    CustomerSubscription.customer_id == customer.id,
                    CustomerSubscription.manager_user_id == previous_manager_id,
                )
                .values(manager_user_id=customer.manager_user_id)
            )
        for key in ("region", "contact", "note"):
            if key in data:
                setattr(customer, key, self._clean(data[key]))
        if "first_purchase_at" in data:
            customer.first_purchase_at = _normalize_datetime(data["first_purchase_at"])
        if "is_active" in data:
            customer.is_active = data["is_active"]
        self.log_repo.create_admin_log(admin.id, "update_customer", "customer", customer.name)
        if manager_changed:
            recipients = list(
                self.db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True))).all()
            )
            if previous_manager_id is not None:
                recipients.append(previous_manager_id)
            if customer.manager_user_id is not None:
                recipients.append(customer.manager_user_id)
            changed_at = datetime.now(timezone.utc).isoformat()
            create_admin_notifications(
                self.db,
                kind="manager_assignment",
                title="客户负责人已变更",
                content=f"客户「{customer.name}」的负责经理已变更，请及时跟进。",
                dedupe_key=f"manager-assignment:{customer.id}:{previous_manager_id}:{customer.manager_user_id}:{changed_at}",
                target_type="customer",
                target_id=customer.id,
                recipient_user_ids=list(set(recipients)),
            )
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def bind_account(self, customer: Customer, user_id: int, admin: User) -> Customer:
        """绑定一个启用中的普通用户账号，禁止复用经理或管理员账号。"""

        user = self.user_repo.get_by_id(user_id)
        if user is None or not user.is_active or user.role != "user":
            raise BusinessError("只能绑定启用中的普通用户账号")
        other = self.db.scalar(
            select(Customer).where(
                Customer.account_user_id == user.id,
                Customer.id != customer.id,
            )
        )
        if other is not None:
            raise BusinessError("该用户账号已经绑定其他客户")
        customer.account_user_id = user.id
        self.log_repo.create_admin_log(admin.id, "bind_customer_account", "customer", customer.name)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def create_account(
        self, customer: Customer, username: str, password: str, admin: User
    ) -> Customer:
        """创建普通用户账号并立即绑定到客户档案。"""

        if customer.account_user_id is not None:
            raise BusinessError("该客户已经绑定登录账号")
        normalized_username = username.strip()
        if not normalized_username:
            raise BusinessError("登录用户名不能为空")
        if self.user_repo.get_by_username(normalized_username) is not None:
            raise BusinessError("登录用户名已存在")
        user = self.user_repo.create(
            normalized_username, hash_password(password), role="user"
        )
        self.db.flush()
        customer.account_user_id = user.id
        self.log_repo.create_admin_log(
            admin.id, "create_customer_account", "customer", customer.name
        )
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def unbind_account(self, customer: Customer, admin: User) -> Customer:
        """解除客户绑定，但保留用户账号，避免误删账号影响其他业务。"""

        customer.account_user_id = None
        self.log_repo.create_admin_log(admin.id, "unbind_customer_account", "customer", customer.name)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    @staticmethod
    def to_summary(customer: Customer, subscription_count: int = 0) -> CustomerSummary:
        return CustomerSummary(
            id=customer.id,
            name=customer.name,
            manager_user_id=customer.manager_user_id,
            manager_username=customer.manager.username if customer.manager else None,
            region=customer.region,
            contact=customer.contact,
            note=customer.note,
            first_purchase_at=customer.first_purchase_at,
            is_active=customer.is_active,
            subscription_count=subscription_count,
            created_at=customer.created_at,
            updated_at=customer.updated_at,
            account_user_id=customer.account_user_id,
            account_username=customer.account_user.username if customer.account_user else None,
            account_is_active=customer.account_user.is_active if customer.account_user else None,
        )

    @staticmethod
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    def _validate_manager(self, manager_user_id: int | None) -> int | None:
        """只允许分配给启用中的经理账号。"""

        if manager_user_id is None:
            return None
        manager = self.user_repo.get_by_id(manager_user_id)
        if manager is None or manager.role != "manager" or not manager.is_active:
            raise BusinessError("经理不存在或已停用")
        return manager.id
