"""上游订阅管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.models.user import User
from app.repositories.source_repo import SourceRepository
from app.schemas.common import Page
from app.schemas.source import (
    SourceCreate,
    SourceDetail,
    SourceSummary,
    SourceUpdate,
    SyncResult,
)
from app.services.source_service import SourceService
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=Page[SourceSummary])
def list_sources(
    keyword: str | None = None,
    enabled: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> Page[SourceSummary]:
    """查询上游订阅列表。"""

    items = SourceRepository(db).list(keyword=keyword, enabled=enabled)
    return Page[SourceSummary](
        items=items,
        total=len(items),
        page=1,
        page_size=max(len(items), 1),
    )


@router.post("", response_model=SourceDetail, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """新增上游订阅。"""

    return SourceService(db).create(payload, admin)


@router.post("/sync-all", response_model=list[SyncResult])
def sync_all_sources(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[SyncResult]:
    """手动同步全部启用来源。"""

    service = SyncService(db)
    try:
        return service.sync_all_enabled()
    finally:
        service.client.close()


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """获取单个上游订阅详情。"""

    source = SourceRepository(db).get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="上游订阅不存在")
    return source


@router.put("/{source_id}", response_model=SourceDetail)
def update_source(
    source_id: int,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """修改上游订阅。"""

    source = SourceRepository(db).get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="上游订阅不存在")
    return SourceService(db).update(source, payload, admin)


@router.post("/{source_id}/sync", response_model=SyncResult)
def sync_source(
    source_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> SyncResult:
    """手动同步单个上游。"""

    source = SourceRepository(db).get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="上游订阅不存在")
    service = SyncService(db)
    try:
        return service.sync_source(source)
    finally:
        service.client.close()


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> None:
    """删除上游订阅及其节点。"""

    source = SourceRepository(db).get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="上游订阅不存在")
    SourceService(db).delete(source, admin)
