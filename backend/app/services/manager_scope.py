"""客户订阅的有效经理归属规则。"""

from __future__ import annotations

from sqlalchemy import and_, or_

from app.models.customer import Customer
from app.models.subscription import CustomerSubscription


def subscription_manager_clause(manager_user_id: int):
    """生成订阅查询的有效经理条件。"""

    return or_(
        CustomerSubscription.manager_user_id == manager_user_id,
        and_(
            CustomerSubscription.manager_user_id.is_(None),
            Customer.manager_user_id == manager_user_id,
        ),
    )


def effective_manager_id(subscription: CustomerSubscription) -> int | None:
    """返回订阅指定经理，否则返回客户默认经理。"""

    return subscription.manager_user_id or (
        subscription.customer.manager_user_id if subscription.customer else None
    )
