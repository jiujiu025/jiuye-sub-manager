"""统一节点池数据访问。"""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.node import Node


class NodeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_nodes(
        self,
        *,
        source_id: int | None = None,
        source_name: str | None = None,
        node_type: str | None = None,
        country: str | None = None,
        keyword: str | None = None,
        enabled: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Node], int]:
        conditions = []
        if source_id is not None:
            conditions.append(Node.source_id == source_id)
        if source_name:
            conditions.append(Node.source_name == source_name)
        if node_type:
            conditions.append(Node.type == node_type)
        if country:
            conditions.append(Node.country == country)
        if keyword:
            lowered = keyword.lower()
            conditions.append(
                or_(
                    func.lower(Node.name).contains(lowered),
                    func.lower(Node.original_name).contains(lowered),
                    func.lower(Node.server).contains(lowered),
                )
            )
        if enabled is not None:
            conditions.append(Node.enabled == enabled)

        base = select(Node).where(*conditions)
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.db.scalars(
            base.order_by(Node.id.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(rows), total

    def list_by_source(self, source_id: int) -> list[Node]:
        stmt = select(Node).where(Node.source_id == source_id)
        return list(self.db.scalars(stmt).all())

    def count_by_source(self, source_id: int) -> int:
        return self.db.scalar(
            select(func.count()).select_from(Node).where(Node.source_id == source_id)
        ) or 0

    def delete_by_source(self, source_id: int) -> int:
        result = self.db.execute(delete(Node).where(Node.source_id == source_id))
        return result.rowcount or 0

    def bulk_add(self, nodes: list[Node]) -> None:
        self.db.add_all(nodes)

    def get(self, node_id: int) -> Node | None:
        return self.db.get(Node, node_id)

    def get_by_fingerprint(self, fingerprint: str) -> Node | None:
        return self.db.scalar(
            select(Node).where(Node.node_fingerprint == fingerprint)
        )

    def delete(self, node: Node) -> None:
        # 使用 Core DELETE 立即执行，避免 ORM 延迟删除导致唯一约束插入冲突
        self.db.execute(delete(Node).where(Node.id == node.id))

    def list_enabled_with_filters(
        self,
        *,
        sources: list[str] | None = None,
        countries: list[str] | None = None,
        types: list[str] | None = None,
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
    ) -> list[Node]:
        """按套餐规则查询启用节点，关键词任一匹配即保留。"""

        conditions = [Node.enabled.is_(True)]
        if sources:
            conditions.append(Node.source_name.in_(sources))
        if countries:
            conditions.append(Node.country.in_(countries))
        if types:
            conditions.append(Node.type.in_(types))
        if include_keywords:
            conditions.append(
                or_(
                    *[
                        func.lower(Node.name).contains(keyword.lower())
                        for keyword in include_keywords
                    ]
                )
            )
        if exclude_keywords:
            conditions.append(
                ~or_(
                    *[
                        func.lower(Node.name).contains(keyword.lower())
                        for keyword in exclude_keywords
                    ]
                )
            )
        return list(self.db.scalars(select(Node).where(*conditions)).all())
