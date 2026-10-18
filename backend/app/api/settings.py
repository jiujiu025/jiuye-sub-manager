"""系统设置接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.models.user import User
from app.schemas.settings import (
    NotificationTestRequest,
    SystemSettingsResponse,
    SystemSettingsUpdate,
)
from app.services.notification_delivery_service import (
    NotificationDeliveryError,
    NotificationDeliveryService,
)
from app.services.settings_service import SettingsService
from app.tasks.scheduler import scheduler

router = APIRouter(prefix="/system/settings", tags=["settings"])


@router.get("", response_model=SystemSettingsResponse)
def get_system_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> SystemSettingsResponse:
    """读取当前运行时设置。"""

    return SettingsService(db).get()


@router.put("", response_model=SystemSettingsResponse)
def update_system_settings(
    payload: SystemSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> SystemSettingsResponse:
    """修改运行时设置；同步间隔/缓存 TTL/去重优先级立即生效。"""

    service = SettingsService(db)
    result = service.apply(payload)
    scheduler.apply_runtime_settings(
        result.sync_enabled,
        result.sync_interval_minutes,
        result.health_enabled,
        result.health_interval_minutes,
    )
    return result


@router.post("/test-notification")
def test_notification(
    payload: NotificationTestRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict[str, int | str]:
    """使用当前已保存配置发送一条测试消息。"""

    try:
        sent_count = NotificationDeliveryService(db).send_test(
            payload.channel,
            payload.content,
        )
    except NotificationDeliveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"channel": payload.channel, "sent_count": sent_count}
