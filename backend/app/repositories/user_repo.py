"""管理员用户数据访问。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_username(self, username: str) -> User | None:
        return self.db.scalar(select(User).where(User.username == username))

    def get_any_admin(self) -> User | None:
        """返回任意管理员，用于避免管理员改名后重复初始化。"""

        return self.db.scalar(select(User).where(User.role == "admin").limit(1))

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def list(self, *, role: str | None = None) -> list[User]:
        """按创建时间倒序返回用户，可按角色筛选。"""

        stmt = select(User).order_by(User.created_at.desc())
        if role is not None:
            stmt = stmt.where(User.role == role)
        return list(self.db.scalars(stmt).all())

    def count_active_admins(self) -> int:
        """统计仍可登录的管理员数量。"""

        stmt = select(func.count(User.id)).where(
            User.role == "admin", User.is_active.is_(True)
        )
        return int(self.db.scalar(stmt) or 0)

    def create(self, username: str, password_hash: str, role: str = "admin") -> User:
        user = User(username=username, password_hash=password_hash, role=role)
        self.db.add(user)
        return user
