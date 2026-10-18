"""客户订阅管理接口。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_admin_or_manager
from app.db import get_db
from app.models.user import User
from app.models.subscription import SubscriptionTokenVersion
from app.schemas.subscription import (
    CustomerSubscriptionCreate,
    CustomerSubscriptionCreateResponse,
    CustomerSubscriptionRenew,
    CustomerSubscriptionSummary,
    CustomerSubscriptionUpdate,
    CustomerSubscriptionUrlResponse,
    RestoreSubscriptionTokenRequest,
    SubscriptionTokenVersionSummary,
    SubscriptionLookupRequest,
    SubscriptionLookupResponse,
)
from app.services.customer_subscription_service import CustomerSubscriptionService
from app.services.package_service import display_subscription_name
from app.services.subscription_state import is_effectively_active
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _get_or_404(db: Session, subscription_id: int):
    item = CustomerSubscriptionService(db).get(subscription_id)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    return item


@router.get("", response_model=list[CustomerSubscriptionSummary])
def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_manager),
):
    manager_id = current_user.id if current_user.role == "manager" else None
    return CustomerSubscriptionService(db).list(
        manager_id, include_company_cost=current_user.role == "admin"
    )


@router.post("", response_model=CustomerSubscriptionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(
    payload: CustomerSubscriptionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_or_manager),
):
    if admin.role == "manager":
        payload = payload.model_copy(update={"manager_user_id": admin.id})
    service = CustomerSubscriptionService(db)
    item, token = service.create(payload, admin)
    detail = service.to_summary(service.get(item.id), include_company_cost=admin.role == "admin")
    return CustomerSubscriptionCreateResponse(
        **detail.model_dump(), token=token, subscription_url=service.subscription_url(token)
    )


@router.post("/lookup", response_model=SubscriptionLookupResponse)
def lookup_subscription(
    payload: SubscriptionLookupRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """管理员按 Token 或订阅链接查找客户订阅和历史套餐。"""

    result = SubscriptionService(db).find_subscription_by_token(payload.query)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到匹配的订阅记录")
    kind, item = result
    historical = kind == "customer_subscription_history"
    if historical:
        version = item
        subscription = version.subscription
        return SubscriptionLookupResponse(
            kind="customer_subscription",
            id=subscription.id,
            package_name=subscription.package.name,
            customer_name=subscription.customer.name,
            manager_username=(
                subscription.manager.username
                if subscription.manager
                else (subscription.customer.manager.username if subscription.customer.manager else None)
            ),
            status="historical",
            expires_at=subscription.expires_at,
            note=subscription.note,
            token_prefix=version.token_prefix,
            historical=True,
            history_id=version.id,
            token_revoked_at=version.valid_to,
            created_at=version.created_at,
            updated_at=subscription.updated_at,
        )
    if kind == "customer_subscription":
        return SubscriptionLookupResponse(
            kind=kind,
            id=item.id,
            package_name=item.package.name,
            customer_name=item.customer.name,
            manager_username=item.manager.username if item.manager else (item.customer.manager.username if item.customer.manager else None),
            status=("active" if is_effectively_active(item) else ("revoked" if item.token and item.token.revoked_at else item.status)),
            expires_at=item.expires_at,
            note=item.note,
            token_prefix=item.token.token_prefix,
            historical=False,
            token_revoked_at=item.token.revoked_at if item.token else None,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
    return SubscriptionLookupResponse(
        kind=kind,
        id=item.id,
        package_name=display_subscription_name(item),
        customer_name=item.owner_customer.name if item.owner_customer else None,
        manager_username=None,
        status=("active" if item.enabled and item.token_revoked_at is None else ("revoked" if item.token_revoked_at else "disabled")),
        expires_at=item.expires_at,
        note=item.description,
        token_prefix=item.token_prefix,
        token_revoked_at=item.token_revoked_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/{subscription_id}/token-history", response_model=list[SubscriptionTokenVersionSummary])
def list_token_history(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_manager),
):
    """查看当前订阅的 Token 版本历史，只返回脱敏信息。"""

    manager_id = current_user.id if current_user.role == "manager" else None
    service = CustomerSubscriptionService(db)
    item = service.get(subscription_id, manager_id)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    return [
        SubscriptionTokenVersionSummary(
            id=row.id,
            subscription_id=row.subscription_id,
            token_prefix=row.token_prefix,
            token_mode=row.token_mode,
            source_package_id=row.source_package_id,
            version=row.version,
            action=row.action,
            actor_user_id=row.actor_user_id,
            actor_username=row.actor.username if row.actor else None,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            reason=row.reason,
            created_at=row.created_at,
        )
        for row in service.list_token_history(item)
    ]


@router.get("/{subscription_id}", response_model=CustomerSubscriptionSummary)
def get_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_manager),
):
    manager_id = current_user.id if current_user.role == "manager" else None
    item = CustomerSubscriptionService(db).get(subscription_id, manager_id)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    return CustomerSubscriptionService.to_summary(
        item, include_company_cost=current_user.role == "admin"
    )


@router.post("/{subscription_id}/restore-token", response_model=CustomerSubscriptionCreateResponse)
def restore_token(
    subscription_id: int,
    payload: RestoreSubscriptionTokenRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """管理员恢复一个历史 Token，并返回新的当前订阅地址。"""

    service = CustomerSubscriptionService(db)
    item = service.get(subscription_id)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    version = db.get(SubscriptionTokenVersion, payload.version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Token 历史记录不存在")
    token = service.restore_token(item, version, admin, payload.reason)
    detail = service.to_summary(service.get(item.id), include_company_cost=True)
    return CustomerSubscriptionCreateResponse(
        **detail.model_dump(), token=token, subscription_url=service.subscription_url(token)
    )


@router.get("/{subscription_id}/subscription-url", response_model=CustomerSubscriptionUrlResponse)
def get_subscription_url(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_manager),
):
    manager_id = current_user.id if current_user.role == "manager" else None
    item = CustomerSubscriptionService(db).get(subscription_id, manager_id)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    if item.token is None or item.token.revoked_at is not None:
        raise HTTPException(status_code=404, detail="当前订阅 Token 已失效")
    from app.core.security import decrypt_secret

    try:
        token = decrypt_secret(item.token.token_encrypted)
    except Exception:
        raise HTTPException(status_code=404, detail="当前订阅 Token 不可用") from None
    return CustomerSubscriptionUrlResponse(
        subscription_id=item.id,
        subscription_url=CustomerSubscriptionService.subscription_url(token),
    )


@router.put("/{subscription_id}", response_model=CustomerSubscriptionSummary)
def update_subscription(
    subscription_id: int,
    payload: CustomerSubscriptionUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_or_manager),
):
    manager_id = admin.id if admin.role == "manager" else None
    item = CustomerSubscriptionService(db).get(subscription_id, manager_id)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    if admin.role == "manager":
        payload = payload.model_copy(update={"manager_user_id": admin.id})
    return CustomerSubscriptionService.to_summary(
        CustomerSubscriptionService(db).update(item, payload, admin),
        include_company_cost=admin.role == "admin",
    )


@router.post("/{subscription_id}/regenerate-token", response_model=CustomerSubscriptionCreateResponse)
def regenerate_token(
    subscription_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_or_manager),
):
    service = CustomerSubscriptionService(db)
    item = service.get(subscription_id, admin.id if admin.role == "manager" else None)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    token = service.regenerate_token(item, admin)
    detail = service.to_summary(service.get(item.id), include_company_cost=admin.role == "admin")
    return CustomerSubscriptionCreateResponse(
        **detail.model_dump(), token=token, subscription_url=service.subscription_url(token)
    )


@router.post("/{subscription_id}/revoke-token", response_model=CustomerSubscriptionSummary)
def revoke_token(
    subscription_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_or_manager),
):
    service = CustomerSubscriptionService(db)
    item = service.get(subscription_id, admin.id if admin.role == "manager" else None)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    service.revoke_token(item, admin)
    return CustomerSubscriptionService.to_summary(
        service.get(item.id), include_company_cost=admin.role == "admin"
    )


@router.post("/{subscription_id}/renew", response_model=CustomerSubscriptionSummary)
def renew_subscription(
    subscription_id: int,
    payload: CustomerSubscriptionRenew,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_admin_or_manager),
):
    service = CustomerSubscriptionService(db)
    item = service.get(subscription_id, actor.id if actor.role == "manager" else None)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    return CustomerSubscriptionService.to_summary(
        service.renew(item, payload, actor), include_company_cost=actor.role == "admin"
    )


@router.post("/{subscription_id}/suspend", response_model=CustomerSubscriptionSummary)
def suspend_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_admin_or_manager),
):
    service = CustomerSubscriptionService(db)
    item = service.get(subscription_id, actor.id if actor.role == "manager" else None)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    return CustomerSubscriptionService.to_summary(
        service.change_status(item, "paused", actor), include_company_cost=actor.role == "admin"
    )


@router.post("/{subscription_id}/resume", response_model=CustomerSubscriptionSummary)
def resume_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_admin_or_manager),
):
    service = CustomerSubscriptionService(db)
    item = service.get(subscription_id, actor.id if actor.role == "manager" else None)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    return CustomerSubscriptionService.to_summary(
        service.change_status(item, "active", actor), include_company_cost=actor.role == "admin"
    )


@router.post("/{subscription_id}/cancel", response_model=CustomerSubscriptionSummary)
def cancel_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_admin_or_manager),
):
    service = CustomerSubscriptionService(db)
    item = service.get(subscription_id, actor.id if actor.role == "manager" else None)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    return CustomerSubscriptionService.to_summary(
        service.change_status(item, "cancelled", actor), include_company_cost=actor.role == "admin"
    )
