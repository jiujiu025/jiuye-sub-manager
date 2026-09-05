"""上游订阅数据访问。"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.source import Source


class SourceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        keyword: str | None = None,
        enabled: bool | None = None,
    ) -> list[Source]:
        stmt = select(Source).order_by(Source.created_at.desc())
        if keyword:
            stmt = stmt.where(
                or_(Source.name.contains(keyword), Source.url.contains(keyword))
            )
        if enabled is not None:
            stmt = stmt.where(Source.enabled == enabled)
        return list(self.db.scalars(stmt).all())

    def list_enabled(self) -> list[Source]:
        stmt = select(Source).where(Source.enabled.is_(True)).order_by(Source.created_at)
        return list(self.db.scalars(stmt).all())

    def get(self, source_id: int) -> Source | None:
        return self.db.get(Source, source_id)

    def get_by_name(self, name: str) -> Source | None:
        return self.db.scalar(select(Source).where(Source.name == name))

    def create(
        self,
        *,
        name: str,
        url: str,
        enabled: bool,
        allow_empty_override: bool,
        fmt: str,
    ) -> Source:
        source = Source(
            name=name,
            url=url,
            enabled=enabled,
            allow_empty_override=allow_empty_override,
            format=fmt,
        )
        self.db.add(source)
        return source

    def delete(self, source: Source) -> None:
        self.db.delete(source)
