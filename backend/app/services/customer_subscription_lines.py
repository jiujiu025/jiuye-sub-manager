"""客户订阅线路明细的创建、补齐和到期判断。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.subscription import CustomerSubscription, CustomerSubscriptionLine
from app.services.package_service import PackageService


def utc(value: datetime | None) -> datetime | None:
    """把数据库中的无时区时间按 UTC 解释。"""

    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def list_lines(db: Session, subscription_id: int) -> list[CustomerSubscriptionLine]:
    """按套餐原有顺序读取客户订阅线路。"""

    return list(
        db.scalars(
            select(CustomerSubscriptionLine)
            .options(joinedload(CustomerSubscriptionLine.node))
            .where(CustomerSubscriptionLine.subscription_id == subscription_id)
            .order_by(CustomerSubscriptionLine.position.asc(), CustomerSubscriptionLine.id.asc())
        ).all()
    )


def ensure_lines(
    db: Session,
    subscription: CustomerSubscription,
) -> list[CustomerSubscriptionLine]:
    """为新订阅或历史订阅建立线路快照；重复调用不会重复创建。"""

    existing = list_lines(db, subscription.id)
    if existing:
        return existing

    previews = PackageService(db).preview(subscription.package)
    for position, preview in enumerate(previews):
        db.add(
            CustomerSubscriptionLine(
                subscription_id=subscription.id,
                node_id=preview.id,
                position=position,
                remark=preview.name,
                expires_at=utc(subscription.expires_at),
                status="active",
            )
        )
    db.flush()
    return list_lines(db, subscription.id)


def is_expired(
    line: CustomerSubscriptionLine,
    node=None,
    now: datetime | None = None,
) -> bool:
    """判断线路是否到期；空时间表示长期有效。"""

    if line.expires_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    expires_at = utc(line.expires_at)
    if expires_at is not None and expires_at <= current:
        return True
    node_expires_at = utc(getattr(node, "expires_at", None))
    return node_expires_at is not None and node_expires_at <= current


def to_summary(line: CustomerSubscriptionLine) -> dict:
    """转换为 API 可返回的线路摘要。"""

    return {
        "id": line.id,
        "subscription_id": line.subscription_id,
        "node_id": line.node_id,
        "position": line.position,
        "remark": line.remark,
        "expires_at": utc(line.expires_at),
        "status": "expired" if is_expired(line, line.node) else line.status,
        "created_at": utc(line.created_at),
        "updated_at": utc(line.updated_at),
    }
