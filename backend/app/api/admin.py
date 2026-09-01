"""管理员认证接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, PasswordChangeRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """管理员登录，返回 JWT。"""

    return AuthService(db).login(payload.username, payload.password)


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
