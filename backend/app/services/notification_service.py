"""站内通知生成与读取业务逻辑。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import BusinessError
from app.models.notification import Notification
from app.models.subscription import CustomerSubscription
from app.services.manager_scope import effective_manager_id
from app.services.subscription_state import active_subscription_clause
from app.models.user import User


def _utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_expiry_notifications(self, now: datetime | None = None) -> int:
        """补齐未来三天内到期的提醒，并通过去重键保证幂等。"""

        current = now or datetime.now(timezone.utc)
        window_end = current + timedelta(days=3)
        subscriptions = self.db.scalars(
            select(CustomerSubscription)
            .options(
                joinedload(CustomerSubscription.customer),
                joinedload(CustomerSubscription.package),
            )
            .outerjoin(CustomerSubscription.token)
            .where(
                active_subscription_clause(current),
                CustomerSubscription.expires_at > current,
                CustomerSubscription.expires_at <= window_end,
            )
        ).all()
        active_admins = self.db.scalars(
            select(User).where(User.role == "admin", User.is_active.is_(True))
        ).all()
        created = 0
        for subscription in subscriptions:
            expires_at = _utc(subscription.expires_at)
            if expires_at is None:
                continue
            recipients = [user.id for user in active_admins]
            manager_id = effective_manager_id(subscription)
            if manager_id is not None:
                recipients.append(manager_id)
            customer_account_id = subscription.customer.account_user_id
            if customer_account_id is not None and subscription.customer.is_active:
                recipients.append(customer_account_id)
            is_today = expires_at.date() == current.date()
            notification_kind = (
                "subscription_expiry_today" if is_today else "subscription_expiry"
            )
            title = "订阅今日到期" if is_today else "订阅即将到期"
            priority = "high" if is_today or expires_at <= current + timedelta(days=1) else "normal"
            dedupe_stamp = f"{notification_kind}:{expires_at.isoformat()}"
            for recipient_id in recipients:
                if recipient_id is None:
                    continue
                dedupe_key = f"expiry:{subscription.id}:{recipient_id}:{dedupe_stamp}"
                try:
                    # 唯一键负责最终幂等；嵌套事务把并发插入冲突转换为“已存在”。
                    with self.db.begin_nested():
                        self.db.add(
                            Notification(
                                recipient_user_id=recipient_id,
                                subscription_id=subscription.id,
                                kind=notification_kind,
                                priority=priority,
                                dedupe_key=dedupe_key,
                                title=title,
                                content=(
                                    f"客户「{subscription.customer.name}」的套餐「{subscription.package.name}」"
                                    f"将于 {expires_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC 到期。"
                                ),
                                target_type="subscription",
                                target_id=subscription.id,
                            )
                        )
                        self.db.flush()
                    created += 1
                except IntegrityError:
                    continue
        if created:
            self.db.commit()
        return created

    def list_for_user(
        self,
        user: User,
        *,
        status: str = "all",
        kind: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int, int]:
        self.ensure_expiry_notifications()
        base = select(Notification)
        unread_statement = select(func.count(Notification.id)).where(
            Notification.read_at.is_(None), Notification.archived_at.is_(None)
        )
        # 管理员也按自己的收件人记录读取，避免一个管理员“全部已读”影响其他管理员。
        base = base.where(Notification.recipient_user_id == user.id)
        unread_statement = unread_statement.where(Notification.recipient_user_id == user.id)
        if kind:
            unread_statement = unread_statement.where(Notification.kind == kind)
        if status != "archived":
            base = base.where(Notification.archived_at.is_(None))
        if status == "unread":
            base = base.where(Notification.read_at.is_(None))
        elif status == "read":
            base = base.where(Notification.read_at.is_not(None))
        elif status == "archived":
            base = base.where(Notification.archived_at.is_not(None))
        if kind:
            base = base.where(Notification.kind == kind)
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = self.db.scalars(base.order_by(
            Notification.created_at.desc(), Notification.id.desc()
        ).offset((page - 1) * page_size).limit(page_size)).all()
        unread_count = self.db.scalar(unread_statement) or 0
        return list(rows), int(unread_count), total

    def mark_read(self, notification_id: int, user: User) -> Notification:
        notification = self.db.get(Notification, notification_id)
        if notification is None or notification.recipient_user_id != user.id:
            raise BusinessError("通知不存在", status_code=404)
        notification.read_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def mark_all_read(self, user: User) -> int:
        statement = update(Notification).where(Notification.read_at.is_(None))
        statement = statement.where(Notification.recipient_user_id == user.id)
        result = self.db.execute(statement.values(read_at=datetime.now(timezone.utc)))
        self.db.commit()
        return int(result.rowcount or 0)

    def archive(self, notification_id: int, user: User) -> Notification:
        notification = self.db.get(Notification, notification_id)
        if notification is None or notification.recipient_user_id != user.id:
            raise BusinessError("通知不存在", status_code=404)
        notification.archived_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def archive_stale(self, days: int = 90) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = self.db.execute(
            update(Notification)
            .where(Notification.created_at < cutoff, Notification.archived_at.is_(None))
            .values(archived_at=datetime.now(timezone.utc))
        )
        self.db.commit()
        return int(result.rowcount or 0)
