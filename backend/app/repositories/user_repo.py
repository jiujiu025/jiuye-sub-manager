"""管理员用户数据访问。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_username(self, username: str) -> User | None:
        return self.db.scalar(select(User).where(User.username == username))

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def create(self, username: str, password_hash: str, role: str = "admin") -> User:
        user = User(username=username, password_hash=password_hash, role=role)
        self.db.add(user)
        return user
