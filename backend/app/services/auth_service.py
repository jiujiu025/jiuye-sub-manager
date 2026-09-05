"""管理员认证业务逻辑。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.log_repo = LogRepository(db)

    def authenticate(self, username: str, password: str) -> User:
        user = self.user_repo.get_by_username(username)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        return user

    def login(self, username: str, password: str) -> TokenResponse:
        user = self.authenticate(username, password)
        token = create_access_token(user.username)
        self.log_repo.create_admin_log(
            admin_user_id=user.id,
            action="login",
            target_type="user",
            target_value=user.username,
        )
        self.db.commit()
        return TokenResponse(access_token=token)

    def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not verify_password(old_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="旧密码错误",
            )
        user.password_hash = hash_password(new_password)
        self.log_repo.create_admin_log(
            admin_user_id=user.id,
            action="change_password",
            target_type="user",
            target_value=user.username,
        )
        self.db.commit()
