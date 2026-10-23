"""日志查询接口。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_admin_or_manager
from app.db import get_db
from app.models.user import User
from app.repositories.log_repo import LogRepository
from app.schemas.log import AdminLogResponse, SubscriptionLogResponse, SyncLogResponse
from app.utils.log_reader import read_log_tail

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
def get_logs(
    kind: Literal["sync", "subscription", "admin", "three_xui", "system", "error"] = "sync",
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    """按类型查询日志；sync/subscription/admin 读数据库，system/error 读日志文件。"""

    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, 100))
    repo = LogRepository(db)
    if kind == "sync":
        items, total = repo.list_sync_logs(safe_page, safe_page_size)
        return {
            "items": [SyncLogResponse.model_validate(item) for item in items],
            "total": total,
        }
    if kind == "subscription":
        items, total = repo.list_subscription_logs(safe_page, safe_page_size)
        return {
            "items": [
                SubscriptionLogResponse.model_validate(item) for item in items
            ],
            "total": total,
        }
    if kind == "admin":
        items, total = repo.list_admin_logs(safe_page, safe_page_size)
        return {
            "items": [AdminLogResponse.model_validate(item) for item in items],
            "total": total,
        }
    if kind == "three_xui":
        items, total = repo.list_three_xui_logs(safe_page, safe_page_size)
        return {
            "items": [AdminLogResponse.model_validate(item) for item in items],
            "total": total,
        }
    error_only = kind == "error"
    lines = read_log_tail(safe_page_size, error_only=error_only)
    return {"items": lines, "total": len(lines)}


@router.get("/manager")
def get_manager_logs(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    manager: User = Depends(get_current_admin_or_manager),
) -> dict:
    """读取经理自己的操作审计日志；管理员可按同一接口查看自己的操作。"""

    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, 100))
    items, total = LogRepository(db).list_admin_logs(
        safe_page,
        safe_page_size,
        admin_user_id=manager.id,
    )
    return {
        "items": [AdminLogResponse.model_validate(item) for item in items],
        "total": total,
    }
