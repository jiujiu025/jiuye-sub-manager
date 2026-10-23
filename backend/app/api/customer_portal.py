"""客户登录后的只读门户接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.package import PreviewNode
from app.schemas.notification import NotificationListResponse, NotificationSummary
from app.schemas.subscription import (
    CustomerPortalProfile,
    CustomerPortalSubscription,
    CustomerSubscriptionUrlResponse,
)
from app.services.customer_subscription_service import CustomerSubscriptionService
from app.services.package_service import PackageService
from app.services.subscription_state import effective_subscription_status, is_effectively_active
from app.services.notification_service import NotificationService
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/customer", tags=["customer-portal"])


def _get_customer(db: Session, user: User) -> Customer | None:
    """只允许普通用户通过绑定关系访问客户档案。"""

    if user.role != "user":
        raise HTTPException(status_code=403, detail="客户门户仅供普通用户使用")
    return db.query(Customer).filter(Customer.account_user_id == user.id).first()


def _portal_summary(item) -> CustomerPortalSubscription:
    token = item.token
    if token is None:
        raise HTTPException(status_code=404, detail="客户订阅 Token 不存在")
    return CustomerPortalSubscription(
        id=item.id,
        package_id=item.package_id,
        package_name=item.package.name,
        status=effective_subscription_status(item),
        started_at=item.started_at,
        expires_at=item.expires_at,
        token_prefix=token.token_prefix,
        token_created_at=token.created_at,
        token_revoked_at=token.revoked_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/me", response_model=CustomerPortalProfile)
def customer_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomerPortalProfile:
    """返回绑定状态；未绑定时不泄露任何客户数据。"""

    customer = _get_customer(db, user)
    if customer is None:
        return CustomerPortalProfile(bound=False)
    return CustomerPortalProfile(
        bound=True,
        customer_id=customer.id,
        name=customer.name,
        region=customer.region,
        manager_username=customer.manager.username if customer.manager else None,
    )


@router.get("/subscriptions", response_model=list[CustomerPortalSubscription])
def list_customer_subscriptions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CustomerPortalSubscription]:
    """返回当前客户的订阅，不返回财务字段。"""

    customer = _get_customer(db, user)
    if customer is None:
        return []
    service = CustomerSubscriptionService(db)
    return [_portal_summary(item) for item in service.list_for_customer(customer.id)]


@router.get("/notifications", response_model=NotificationListResponse)
def list_customer_notifications(
    status: str = "all",
    kind: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationListResponse:
    """客户只能读取发给自己账号的站内通知。"""

    if _get_customer(db, user) is None:
        raise HTTPException(status_code=404, detail="客户档案未绑定")
    if status not in {"all", "unread", "read", "archived"}:
        raise HTTPException(status_code=422, detail="通知状态参数无效")
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="分页参数无效")
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


@router.post("/notifications/read-all")
def mark_all_customer_notifications_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """将当前客户自己的通知全部标记为已读。"""

    if _get_customer(db, user) is None:
        raise HTTPException(status_code=404, detail="客户档案未绑定")
    return {"marked_count": NotificationService(db).mark_all_read(user)}


@router.post("/notifications/{notification_id}/read", response_model=NotificationSummary)
def mark_customer_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationSummary:
    """客户只能标记发给自己的通知。"""

    if _get_customer(db, user) is None:
        raise HTTPException(status_code=404, detail="客户档案未绑定")
    item = NotificationService(db).mark_read(notification_id, user)
    return NotificationSummary.model_validate(item)


@router.get("/subscriptions/{subscription_id}", response_model=CustomerPortalSubscription)
def get_customer_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomerPortalSubscription:
    """按客户 ID 二次校验订阅归属，防止 IDOR。"""

    customer = _get_customer(db, user)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户档案未绑定")
    item = CustomerSubscriptionService(db).get_for_customer(subscription_id, customer.id)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    return _portal_summary(item)


@router.get(
    "/subscriptions/{subscription_id}/subscription-url",
    response_model=CustomerSubscriptionUrlResponse,
)
def get_customer_subscription_url(
    subscription_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomerSubscriptionUrlResponse:
    """仅在受保护请求中按需返回当前客户自己的订阅地址。"""

    customer = _get_customer(db, user)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户档案未绑定")
    item = CustomerSubscriptionService(db).get_for_customer(subscription_id, customer.id)
    if item is None or item.token is None or item.token.revoked_at is not None:
        raise HTTPException(status_code=404, detail="客户订阅不存在或 Token 已失效")
    return CustomerSubscriptionUrlResponse(
        subscription_id=item.id,
        subscription_url=CustomerSubscriptionService.subscription_url_from_item(item),
    )


@router.get("/subscriptions/{subscription_id}/preview", response_model=list[PreviewNode])
def preview_customer_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PreviewNode]:
    """返回脱敏节点摘要，不返回 UUID、密码和私钥。"""

    customer = _get_customer(db, user)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户档案未绑定")
    item = CustomerSubscriptionService(db).get_for_customer(subscription_id, customer.id)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    if not is_effectively_active(item):
        raise HTTPException(status_code=404, detail="客户订阅已失效")
    return SubscriptionService(db).preview_customer(item)
