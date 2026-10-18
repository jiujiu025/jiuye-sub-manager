"""通知写入辅助逻辑，避免业务服务之间产生循环依赖。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User


def create_admin_notifications(
    db: Session,
    *,
    kind: str,
    title: str,
    content: str,
    dedupe_key: str,
    priority: str = "normal",
    target_type: str | None = None,
    target_id: int | None = None,
    recipient_user_ids: list[int] | None = None,
) -> int:
    """为管理员或指定业务人员创建通知；通过去重键避免重复刷屏。"""

    if recipient_user_ids is None:
        recipient_user_ids = list(
            db.scalars(
                select(User.id).where(User.role == "admin", User.is_active.is_(True))
            ).all()
        )
    created = 0
    for recipient_id in recipient_user_ids:
        recipient_key = f"{dedupe_key}:{recipient_id}"
        try:
            # 不能只依赖“先查询再插入”，并发任务仍可能同时通过查询。
            # 数据库唯一键负责最终幂等，冲突时只跳过当前接收人。
            with db.begin_nested():
                db.add(
                    Notification(
                        recipient_user_id=recipient_id,
                        kind=kind,
                        priority=priority,
                        dedupe_key=recipient_key,
                        title=title,
                        content=content,
                        subscription_id=target_id if target_type == "subscription" else None,
                        target_type=target_type,
                        target_id=target_id,
                    )
                )
                db.flush()
            created += 1
        except IntegrityError:
            continue
    return created
