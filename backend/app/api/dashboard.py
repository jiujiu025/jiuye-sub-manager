"""后台概览接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardStats
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> DashboardStats:
    """后台首页统计。"""

    return DashboardService(db).stats()
