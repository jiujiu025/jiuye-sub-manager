"""上游订阅业务逻辑。"""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.models.source import Source
from app.models.package import PackageRule
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.source_repo import SourceRepository
from app.schemas.source import SourceCreate, SourceUpdate


def validate_source_url(url: str) -> None:
    """校验上游订阅 URL 必须是合法 http/https 地址。"""

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise BusinessError("订阅 URL 必须是有效的 http/https 地址")


class SourceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SourceRepository(db)
        self.node_repo = NodeRepository(db)
        self.log_repo = LogRepository(db)

    def create(self, payload: SourceCreate, admin: User) -> Source:
        validate_source_url(payload.url)
        if self.repo.get_by_name(payload.name) is not None:
            raise BusinessError("订阅名称已存在")
        source = self.repo.create(
            name=payload.name,
            url=payload.url,
            enabled=payload.enabled,
            allow_empty_override=payload.allow_empty_override,
            fmt=payload.format,
        )
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="create_source",
            target_type="source",
            target_value=source.name,
        )
        self.db.commit()
        self.db.refresh(source)
        return source

    def update(self, source: Source, payload: SourceUpdate, admin: User) -> Source:
        data = payload.model_dump(exclude_unset=True)
        if "url" in data:
            validate_source_url(data["url"])
        if "name" in data and data["name"] != source.name:
            if self.repo.get_by_name(data["name"]) is not None:
                raise BusinessError("订阅名称已存在")
            old_name = source.name
            new_name = data["name"]
            for node in self.node_repo.list_by_source(source.id):
                node.source_name = new_name
            for rule in self.db.scalars(select(PackageRule)).all():
                if isinstance(rule.source_filter, list):
                    rule.source_filter = [
                        new_name if value == old_name else value
                        for value in rule.source_filter
                    ]
        for key, value in data.items():
            setattr(source, key, value)
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="update_source",
            target_type="source",
            target_value=source.name,
        )
        self.db.commit()
        self.db.refresh(source)
        return source

    def delete(self, source: Source, admin: User) -> None:
        self.node_repo.delete_by_source(source.id)
        self.log_repo.create_admin_log(
            admin_user_id=admin.id,
            action="delete_source",
            target_type="source",
            target_value=source.name,
        )
        self.repo.delete(source)
        self.db.commit()
