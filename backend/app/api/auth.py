"""普通用户认证与只读账户接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import (
    RATE_LIMIT_MESSAGE,
    rate_limiter,
    request_client_ip,
    stable_rate_key,
)
from app.db import get_db
from app.models.user import User
from app.repositories.package_repo import PackageRepository
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.schemas.package import PackageDetail, PackageSubscriptionUrlResponse
from app.services.auth_service import AuthService
from app.services.package_service import PackageService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """通用登录入口，返回管理员或普通用户角色。"""

    settings = get_settings()
    key = stable_rate_key(
        "user-login", request_client_ip(request), payload.username.strip().lower()
    )
    decision = rate_limiter.check(
        key, settings.login_rate_limit, settings.login_rate_window_seconds
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMIT_MESSAGE,
            headers={"Retry-After": str(decision.retry_after)},
        )
    try:
        result = AuthService(db).login(payload.username, payload.password)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            rate_limiter.hit(
                key, settings.login_rate_limit, settings.login_rate_window_seconds
            )
        raise
    rate_limiter.clear(key)
    return result


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> User:
    """返回当前普通用户或管理员资料。"""

    return current_user


@router.get("/packages", response_model=list[PackageDetail])
def list_my_packages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PackageDetail]:
    """只返回当前用户归属的套餐。"""

    packages = PackageRepository(db).list_for_owner(current_user.id)
    service = PackageService(db)
    return [service.to_detail(package) for package in packages]


@router.get("/packages/{package_id}", response_model=PackageDetail)
def get_my_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PackageDetail:
    """返回当前用户自己的套餐详情。"""

    package = PackageRepository(db).get(package_id)
    if package is None or package.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="套餐不存在")
    return PackageService(db).to_detail(package)


@router.get(
    "/packages/{package_id}/subscription-url",
    response_model=PackageSubscriptionUrlResponse,
)
def get_my_subscription_url(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PackageSubscriptionUrlResponse:
    """普通用户按需获取自己套餐的订阅地址。"""

    package = PackageRepository(db).get(package_id)
    if package is None or package.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="套餐不存在")
    url = PackageService.subscription_url(package)
    if url is None:
        raise HTTPException(status_code=404, detail="当前套餐没有可用订阅 Token")
    return PackageSubscriptionUrlResponse(package_id=package.id, subscription_url=url)
