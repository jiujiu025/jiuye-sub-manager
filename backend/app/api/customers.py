"""客户档案管理接口。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_admin_or_manager
from app.db import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.customer import (
    CustomerAccountBind,
    CustomerAccountCreate,
    CustomerCreate,
    CustomerSummary,
    CustomerUpdate,
)
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerSummary])
def list_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_manager),
):
    manager_id = current_user.id if current_user.role == "manager" else None
    return CustomerService(db).list(manager_id)


@router.post("", response_model=CustomerSummary, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_or_manager),
):
    if admin.role == "manager":
        payload = payload.model_copy(update={"manager_user_id": admin.id})
    customer = CustomerService(db).create(payload, admin)
    return CustomerService.to_summary(customer)


@router.put("/{customer_id}", response_model=CustomerSummary)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_or_manager),
):
    customer = db.get(Customer, customer_id)
    if customer is None or (
        admin.role == "manager" and customer.manager_user_id != admin.id
    ):
        raise HTTPException(status_code=404, detail="客户不存在")
    if admin.role == "manager":
        payload = payload.model_copy(update={"manager_user_id": admin.id})
    updated = CustomerService(db).update(customer, payload, admin)
    return CustomerService.to_summary(updated)


@router.post("/{customer_id}/account/bind", response_model=CustomerSummary)
def bind_customer_account(
    customer_id: int,
    payload: CustomerAccountBind,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """绑定已有普通用户账号；经理不能执行账号绑定。"""

    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    return CustomerService.to_summary(
        CustomerService(db).bind_account(customer, payload.user_id, admin),
        subscription_count=len(customer.subscriptions),
    )


@router.post("/{customer_id}/account/create", response_model=CustomerSummary)
def create_customer_account(
    customer_id: int,
    payload: CustomerAccountCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """为客户创建新的普通用户登录账号并自动绑定。"""

    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    return CustomerService.to_summary(
        CustomerService(db).create_account(customer, payload.username, payload.password, admin),
        subscription_count=len(customer.subscriptions),
    )


@router.delete("/{customer_id}/account", response_model=CustomerSummary)
def unbind_customer_account(
    customer_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """解除客户与登录账号的绑定，但不删除用户账号。"""

    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    return CustomerService.to_summary(
        CustomerService(db).unbind_account(customer, admin),
        subscription_count=len(customer.subscriptions),
    )
