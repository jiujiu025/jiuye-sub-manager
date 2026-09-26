"""套餐数据访问。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.package import Package


class PackageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[Package]:
        stmt = select(Package).order_by(Package.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def list_for_owner(self, owner_user_id: int) -> list[Package]:
        """只返回指定用户拥有的套餐。"""

        stmt = (
            select(Package)
            .where(Package.owner_user_id == owner_user_id)
            .order_by(Package.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get(self, package_id: int) -> Package | None:
        return self.db.get(Package, package_id)

    def get_by_name(self, name: str) -> Package | None:
        return self.db.scalar(select(Package).where(Package.name == name))

    def get_by_token_hash(self, token_hash: str) -> Package | None:
        return self.db.scalar(
            select(Package).where(Package.token_hash == token_hash)
        )

    def create(
        self,
        *,
        name: str,
        subscription_name: str | None,
        enabled: bool,
        description: str | None,
        expires_at: datetime | None,
        token_hash: str,
        token_prefix: str,
        token_encrypted: str,
        owner_user_id: int | None = None,
        token_name: str | None = None,
    ) -> Package:
        package = Package(
            name=name,
            subscription_name=subscription_name,
            enabled=enabled,
            description=description,
            expires_at=expires_at,
            token_hash=token_hash,
            token_prefix=token_prefix,
            token_encrypted=token_encrypted,
            owner_user_id=owner_user_id,
            token_name=token_name,
        )
        self.db.add(package)
        return package

    def delete(self, package: Package) -> None:
        self.db.delete(package)
