"""管理员认证接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.config import get_settings
from app.core.rate_limit import (
    RATE_LIMIT_MESSAGE,
    rate_limiter,
    request_client_ip,
    stable_rate_key,
)
from app.db import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, PasswordChangeRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """管理员登录，返回 JWT。"""

    settings = get_settings()
    key = stable_rate_key(
        "login", request_client_ip(request), payload.username.strip().lower()
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
def me(current_admin: User = Depends(get_current_admin)) -> User:
    """返回当前管理员信息。"""

    return current_admin


@router.put("/password", response_model=None)
def change_password(
    payload: PasswordChangeRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """修改当前管理员密码。"""

    AuthService(db).change_password(current_admin, payload.old_password, payload.new_password)
    return {"detail": "密码修改成功"}
