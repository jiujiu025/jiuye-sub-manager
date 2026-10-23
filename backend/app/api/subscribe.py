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
    # ASCII fallback 兼容不识别 filename* 的客户端；真实名称由 filename* 提供。
    ascii_name = "".join(
        char
        if char.isascii() and (char.isalnum() or char in "._-")
        else "-"
        for char in name
    )
    ascii_name = ascii_name.strip(" ._-") or "subscription"
    extension = "json" if output_format == "singbox" else "txt" if output_format in {"uri", "base64"} else "yaml"
    return f'inline; filename="{ascii_name}.{extension}"; filename*=UTF-8\'\'{encoded}'


def _content_type(output_format: str) -> str:
    """返回客户端可识别且明确带 UTF-8 的内容类型。"""

    return {
        "singbox": "application/json; charset=utf-8",
        "uri": "text/plain; charset=utf-8",
        "base64": "text/plain; charset=utf-8",
    }.get(output_format, "application/yaml; charset=utf-8")


def _subscription_headers(
    package, output_format: str, content: str, expires_at=None
) -> dict[str, str]:
    """构造订阅响应头，阻止浏览器和共享代理持久化 Token 对应内容。"""

    updated_at = package.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    headers = {
        "Content-Type": _content_type(output_format),
        "Content-Disposition": _subscription_disposition(package, output_format),
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "ETag": f'"{hashlib.sha256(content.encode("utf-8")).hexdigest()}"',
        "Last-Modified": format_datetime(
            updated_at.astimezone(timezone.utc), usegmt=True
        ),
        "Profile-Update-Interval": "3600",
        # V2RayN/V2RayNG/Hiddify/NekoBox 等客户端会使用该订阅标题。
        "Profile-Title": quote(display_subscription_name(package), safe=""),
        "X-Subscription-Client": output_format,
        "X-Subscription-Updated-At": updated_at.astimezone(timezone.utc).isoformat(),
        "X-Content-Type-Options": "nosniff",
    }
    effective_expires_at = expires_at if expires_at is not None else package.expires_at
    if effective_expires_at is not None:
        expires_at = effective_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        # 兼容更多客户端的标准订阅用户信息格式；到期时间由客户端自行执行。
        headers["Subscription-Userinfo"] = (
            f"upload=0; download=0; total=0; expire={int(expires_at.timestamp())}"
        )
    return headers


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
    decision = rate_limiter.reserve(
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
    try:
        output_format = resolve_output_format(client, request.headers.get("user-agent"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = SubscriptionService(db)
    customer_subscription = service.resolve_customer_subscription(token)
    package = customer_subscription.package if customer_subscription else service.resolve_package(token)
    if package is None:
        raise HTTPException(status_code=404, detail="订阅不存在")
    if customer_subscription:
        service.record_customer_token_access(customer_subscription, client_ip)
    else:
        service.record_token_access(package, client_ip)
    if not package.enabled:
        raise HTTPException(status_code=403, detail="套餐已禁用")

    if customer_subscription:
        # 在缓存判断前补齐历史订阅线路，避免旧缓存绕过线路级到期规则。
        service.ensure_customer_lines(customer_subscription)

    subscription_expires_at = customer_subscription.expires_at if customer_subscription else None
    is_expired = (
        service.is_expired_at(subscription_expires_at)
        if customer_subscription
        else service.is_expired(package)
    )
    if is_expired:
        content, node_count = service.generate_expired(output_format)
        service.log_subscription(package.id, "expired", node_count, client_ip)
        return Response(
            content=content,
            media_type=_content_type(output_format),
            headers={
                **_subscription_headers(package, output_format, content, subscription_expires_at),
                "X-Subscription-Expired": "true",
            },
        )

    cached_entry = (
        service.get_customer_cached_entry(customer_subscription, output_format)
        if customer_subscription
        else service.get_cached_entry(package, output_format)
    )
    if cached_entry is not None:
        cached, cached_node_count = cached_entry
        service.log_subscription(package.id, "success", cached_node_count, client_ip)
        return Response(
            content=cached,
            media_type=_content_type(output_format),
            headers=_subscription_headers(package, output_format, cached, subscription_expires_at),
        )

    try:
        content, node_count = (
            service.generate_customer(customer_subscription, output_format)
            if customer_subscription
            else service.generate(package, output_format)
        )
    except BusinessError as exc:
        service.log_subscription(package.id, "empty", 0, client_ip)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    if customer_subscription:
        service.set_customer_cached(customer_subscription, content, output_format, node_count)
    else:
        service.set_cached(package, content, output_format, node_count)
    service.log_subscription(package.id, "success", node_count, client_ip)
    return Response(
        content=content,
        media_type=_content_type(output_format),
        headers=_subscription_headers(package, output_format, content, subscription_expires_at),
    )
