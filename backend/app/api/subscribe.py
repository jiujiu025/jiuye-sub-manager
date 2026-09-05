"""公开订阅接口：GET /sub/{token}。"""

from __future__ import annotations

import hashlib
from datetime import timezone
from email.utils import format_datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.db import get_db
from app.exporters import resolve_output_format
from app.core.config import get_settings
from app.core.rate_limit import (
    RATE_LIMIT_MESSAGE,
    rate_limiter,
    request_client_ip,
    stable_rate_key,
)
from app.services.package_service import display_subscription_name
from app.services.subscription_service import SubscriptionService

router = APIRouter(tags=["subscribe"])


def _subscription_disposition(package, output_format: str) -> str:
    """根据订阅显示名称生成 Content-Disposition，不再固定使用 sub.yaml。"""

    name = display_subscription_name(package)
    encoded = quote(name, safe="")
    extension = "json" if output_format == "singbox" else "txt" if output_format == "uri" else "yaml"
    return f'inline; filename="subscription.{extension}"; filename*=UTF-8\'\'{encoded}'


def _content_type(output_format: str) -> str:
    """返回客户端可识别且明确带 UTF-8 的内容类型。"""

    return {
        "singbox": "application/json; charset=utf-8",
        "uri": "text/plain; charset=utf-8",
    }.get(output_format, "application/yaml; charset=utf-8")


def _subscription_headers(package, output_format: str, content: str) -> dict[str, str]:
    """构造订阅响应头，阻止浏览器和共享代理持久化 Token 对应内容。"""

    updated_at = package.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return {
        "Content-Type": _content_type(output_format),
        "Content-Disposition": _subscription_disposition(package, output_format),
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "ETag": f'"{hashlib.sha256(content.encode("utf-8")).hexdigest()}"',
        "Last-Modified": format_datetime(
            updated_at.astimezone(timezone.utc), usegmt=True
        ),
        "X-Content-Type-Options": "nosniff",
    }


@router.get("/sub/{token}")
def get_subscription(
    token: str,
    request: Request,
    client: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    """按 Token 返回客户端所需格式，绝不包含上游订阅 URL。"""

    settings = get_settings()
    client_ip = request_client_ip(request)
    rate_key = stable_rate_key("subscription", client_ip, token)
    decision = rate_limiter.check(
        rate_key,
        settings.subscription_rate_limit,
        settings.subscription_rate_window_seconds,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMIT_MESSAGE,
            headers={"Retry-After": str(decision.retry_after)},
        )
    rate_limiter.hit(
        rate_key,
        settings.subscription_rate_limit,
        settings.subscription_rate_window_seconds,
    )
    try:
        output_format = resolve_output_format(client, request.headers.get("user-agent"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = SubscriptionService(db)
    package = service.resolve_package(token)
    if package is None:
        raise HTTPException(status_code=404, detail="订阅不存在")
    if not package.enabled:
        raise HTTPException(status_code=403, detail="套餐已禁用")

    cached_entry = service.get_cached_entry(package, output_format)
    if cached_entry is not None:
        cached, cached_node_count = cached_entry
        service.log_subscription(package.id, "success", cached_node_count, client_ip)
        return Response(
            content=cached,
            media_type=_content_type(output_format),
            headers=_subscription_headers(package, output_format, cached),
        )

    try:
        content, node_count = service.generate(package, output_format)
    except BusinessError as exc:
        service.log_subscription(package.id, "empty", 0, client_ip)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    service.set_cached(package, content, output_format, node_count)
    service.log_subscription(package.id, "success", node_count, client_ip)
    return Response(
        content=content,
        media_type=_content_type(output_format),
        headers=_subscription_headers(package, output_format, content),
    )
