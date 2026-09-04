"""公开订阅接口：GET /sub/{token}。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.db import get_db
from app.services.package_service import display_subscription_name
from app.services.subscription_service import SubscriptionService

router = APIRouter(tags=["subscribe"])


def _subscription_disposition(package) -> str:
    """根据订阅显示名称生成 Content-Disposition，不再固定使用 sub.yaml。"""

    name = display_subscription_name(package)
    encoded = quote(name, safe="")
    return (
        'attachment; filename="subscription.yaml"; '
        f"filename*=UTF-8''{encoded}"
    )


@router.get("/sub/{token}")
def get_subscription(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """按随机 Token 返回 Clash/Mihomo 配置，绝不包含上游订阅 URL。"""

    service = SubscriptionService(db)
    package = service.resolve_package(token)
    if package is None:
        raise HTTPException(status_code=404, detail="订阅不存在")
    if not package.enabled:
        raise HTTPException(status_code=403, detail="套餐已禁用")

    client_ip = request.client.host if request.client else None
    cached = service.get_cached(package.id)
    if cached is not None:
        service.log_subscription(package.id, "success", 0, client_ip)
        return Response(
            content=cached,
            media_type="text/yaml; charset=utf-8",
            headers={"Content-Disposition": _subscription_disposition(package)},
        )

    try:
        yaml_text, node_count = service.generate_clash(package)
    except BusinessError as exc:
        service.log_subscription(package.id, "empty", 0, client_ip)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    service.set_cached(package.id, yaml_text)
    service.log_subscription(package.id, "success", node_count, client_ip)
    return Response(
        content=yaml_text,
        media_type="text/yaml; charset=utf-8",
        headers={"Content-Disposition": _subscription_disposition(package)},
    )
