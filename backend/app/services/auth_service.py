"""管理员认证业务逻辑。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import ProfileUpdateRequest, TokenResponse, UserCreateRequest, UserUpdateRequest


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.log_repo = LogRepository(db)

    def authenticate(
        self, username: str, password: str, required_role: str | None = None
    ) -> User:
        normalized_username = username.strip()
        user = self.user_repo.get_by_username(normalized_username)
        if (
            user is None
            or not user.is_active
            or (required_role is not None and user.role != required_role)
            or not verify_password(password, user.password_hash)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        return user

    def login(
        self, username: str, password: str, required_role: str | None = None
    ) -> TokenResponse:
        user = self.authenticate(username, password, required_role)
        token = create_access_token(user.username)
        self.log_repo.create_admin_log(
            admin_user_id=user.id,
            action="login",
            target_type="user",
            target_value=user.username,
        )
        self.db.commit()
        return TokenResponse(access_token=token, role=user.role)

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

    def update_profile(self, user: User, payload: ProfileUpdateRequest) -> User:
        """校验当前密码后更新管理员用户名或密码。"""

        if payload.username is None and payload.new_password is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="至少提供新的用户名或密码",
            )
        if not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="当前密码错误",
            )
        if payload.username is not None:
            username = payload.username.strip()
            if not username:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="用户名不能为空",
                )
            existing = self.user_repo.get_by_username(username)
            if existing is not None and existing.id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="用户名已存在",
                )
            user.username = username
        if payload.new_password is not None:
            user.password_hash = hash_password(payload.new_password)
        self.log_repo.create_admin_log(
            admin_user_id=user.id,
            action="update_profile",
            target_type="user",
            target_value=user.username,
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def create_user(self, payload: UserCreateRequest, admin: User) -> User:
        """创建普通用户，普通用户不能通过接口创建管理员。"""

        username = payload.username.strip()
        if not username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名不能为空",
            )
        if self.user_repo.get_by_username(username) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
        user = self.user_repo.create(username, hash_password(payload.password), role="user")
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="create_user",
            target_type="user",
            target_value=username,
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_user(
        self, user: User, payload: UserUpdateRequest, admin: User
    ) -> User:
        """更新普通用户，禁止通过用户管理接口修改管理员。"""

        if user.role != "user":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能管理普通用户")
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可更新的内容")
        if "username" in data:
            username = (data["username"] or "").strip()
            if not username:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名不能为空")
            existing = self.user_repo.get_by_username(username)
            if existing is not None and existing.id != user.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
            user.username = username
        if "password" in data and data["password"] is not None:
            user.password_hash = hash_password(data["password"])
        if "is_active" in data and data["is_active"] is not None:
            user.is_active = data["is_active"]
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="update_user",
            target_type="user",
            target_value=user.username,
        )
        self.db.commit()
        self.db.refresh(user)
        return user
