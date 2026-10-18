"""经理工作台统计查询。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.subscription import CustomerSubscription
from app.models.user import User
from app.schemas.manager import ManagerStats, RegionCount
from app.services.manager_scope import subscription_manager_clause
from app.services.subscription_state import active_subscription_clause


class ManagerService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def stats(self, user: User) -> ManagerStats:
        manager_id = None if user.role == "admin" else user.id
        now = datetime.now(timezone.utc)
        customer_statement = select(func.count(Customer.id))
        if manager_id is not None:
            customer_statement = customer_statement.where(Customer.manager_user_id == manager_id)
        customer_count = int(self.db.scalar(customer_statement) or 0)

        subscription_statement = select(func.count(CustomerSubscription.id)).join(
            CustomerSubscription.customer
        ).outerjoin(CustomerSubscription.token).where(active_subscription_clause(now))
        if manager_id is not None:
            subscription_statement = subscription_statement.where(
                subscription_manager_clause(manager_id)
            )
        active_subscription_count = int(self.db.scalar(subscription_statement) or 0)

        expiring_statement = select(func.count(CustomerSubscription.id)).join(
            CustomerSubscription.customer
        ).outerjoin(CustomerSubscription.token).where(
            active_subscription_clause(now),
            CustomerSubscription.expires_at > now,
            CustomerSubscription.expires_at <= now + timedelta(days=3),
        )
        if manager_id is not None:
            expiring_statement = expiring_statement.where(
                subscription_manager_clause(manager_id)
            )
        expiring_count = int(self.db.scalar(expiring_statement) or 0)

        sales_statement = select(func.coalesce(func.sum(CustomerSubscription.sale_price), 0)).join(
            CustomerSubscription.customer
        ).where(CustomerSubscription.status != "cancelled")
        if manager_id is not None:
            sales_statement = sales_statement.where(subscription_manager_clause(manager_id))
        sales_total = Decimal(str(self.db.scalar(sales_statement) or 0)).quantize(Decimal("0.01"))

        region_statement = (
            select(Customer.region, func.count(func.distinct(Customer.id)))
            .select_from(Customer)
            .outerjoin(CustomerSubscription, CustomerSubscription.customer_id == Customer.id)
            .where(Customer.region.is_not(None))
            .group_by(Customer.region)
            .order_by(func.count(func.distinct(Customer.id)).desc(), Customer.region.asc())
        )
        if manager_id is not None:
            region_statement = region_statement.where(subscription_manager_clause(manager_id))
        regions = [
            RegionCount(region=region or "未填写", customer_count=int(count))
            for region, count in self.db.execute(region_statement).all()
        ]
        return ManagerStats(
            customer_count=customer_count,
            active_subscription_count=active_subscription_count,
            expiring_subscription_count=expiring_count,
            sales_total=sales_total,
            regions=regions,
        )
