"""全部线路查询和 Excel 导出接口。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_or_manager
from app.core.exceptions import BusinessError
from app.db import get_db
from app.models.user import User
from app.schemas.subscription_line import SubscriptionLineExportRequest, SubscriptionLinePage
from app.services.subscription_line_service import SubscriptionLineService

router = APIRouter(prefix="/subscription-lines", tags=["subscription-lines"])


@router.get("", response_model=SubscriptionLinePage)
def list_subscription_lines(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    keyword: str | None = Query(default=None, max_length=128),
    region: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin_or_manager),
) -> SubscriptionLinePage:
    return SubscriptionLineService(db).list_lines(
        manager_user_id=user.id if user.role == "manager" else None,
        page=page,
        page_size=page_size,
        keyword=keyword,
        region=region,
        status=status,
    )


@router.post("/export")
def export_subscription_lines(
    payload: SubscriptionLineExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin_or_manager),
) -> Response:
    content = SubscriptionLineService(db).export_excel(
        payload,
        manager_user_id=user.id if user.role == "manager" else None,
        is_admin=user.role == "admin",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote('客户线路清单.xlsx')}",
            "Cache-Control": "no-store",
        },
    )
