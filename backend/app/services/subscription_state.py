"""客户订阅有效状态判断。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_

from app.models.subscription import CustomerSubscription, SubscriptionToken


def is_effectively_active(
    subscription: CustomerSubscription, now: datetime | None = None
) -> bool:
    """判断订阅是否仍可作为有效订阅统计。"""

    current = now or datetime.now(timezone.utc)
    expires_at = subscription.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return (
        subscription.status == "active"
        and (expires_at is None or expires_at > current)
        and (subscription.token is None or subscription.token.revoked_at is None)
    )


def effective_subscription_status(
    subscription: CustomerSubscription, now: datetime | None = None
) -> str:
    """返回考虑到期和 Token 吊销后的统一展示状态。"""

    if subscription.token is not None and subscription.token.revoked_at is not None:
        return "revoked"
    if subscription.status in {"paused", "cancelled"}:
        return subscription.status
    return "active" if is_effectively_active(subscription, now) else "expired"


def active_subscription_clause(now: datetime):
    """生成数据库查询使用的有效订阅条件。"""

    return and_(
        CustomerSubscription.status == "active",
        or_(CustomerSubscription.expires_at.is_(None), CustomerSubscription.expires_at > now),
        SubscriptionToken.revoked_at.is_(None),
    )
