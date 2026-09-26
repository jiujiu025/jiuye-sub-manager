"""健康检查接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(tags=["system"])


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)) -> dict[str, str]:
    """容器编排与本地健康检查，同时确认数据库可用。"""

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库不可用",
        ) from exc
    return {"status": "ok", "database": "ok"}
