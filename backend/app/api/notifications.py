"""站内收件箱接口。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_or_manager
from app.db import get_db
from app.models.user import User
from app.schemas.notification import NotificationListResponse, NotificationSummary
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    status: str = Query(default="all", pattern="^(all|unread|read|archived)$"),
    kind: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin_or_manager),
):
    items, unread_count, total = NotificationService(db).list_for_user(
        user, status=status, kind=kind, page=page, page_size=page_size
    )
    pages = max(1, (total + page_size - 1) // page_size)
    return NotificationListResponse(
        items=[NotificationSummary.model_validate(item) for item in items],
        unread_count=unread_count,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("/{notification_id}/read", response_model=NotificationSummary)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin_or_manager),
):
    item = NotificationService(db).mark_read(notification_id, user)
    return NotificationSummary.model_validate(item)


@router.post("/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin_or_manager),
):
    count = NotificationService(db).mark_all_read(user)
    return {"marked_count": count}


@router.post("/{notification_id}/archive", response_model=NotificationSummary)
def archive_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin_or_manager),
):
    item = NotificationService(db).archive(notification_id, user)
    return NotificationSummary.model_validate(item)
