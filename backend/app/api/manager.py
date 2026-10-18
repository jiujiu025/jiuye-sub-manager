"""经理工作台接口。"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_or_manager
from app.core.config import get_settings
from app.core.rate_limit import (
    RATE_LIMIT_MESSAGE,
    rate_limiter,
    request_client_ip,
    stable_rate_key,
)
from app.db import get_db
from app.models.user import User
from app.schemas.manager import ManagerStats
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.schemas.package import PreviewNode
from app.schemas.node import NodeExportResponse
from app.services.customer_subscription_service import CustomerSubscriptionService
from app.services.manager_service import ManagerService
from app.services.package_service import PackageService
from app.services.auth_service import AuthService
from app.exporters import export_nodes
from app.repositories.node_repo import NodeRepository
from app.services.subscription_state import is_effectively_active

router = APIRouter(prefix="/manager", tags=["manager"])


@router.post("/login", response_model=TokenResponse)
def manager_login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """经理专用登录入口，与管理员和普通用户入口隔离。"""

    settings = get_settings()
    key = stable_rate_key(
        "manager-login", request_client_ip(request), payload.username.strip().lower()
    )
    decision = rate_limiter.reserve(
        key, settings.login_rate_limit, settings.login_rate_window_seconds
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMIT_MESSAGE,
            headers={"Retry-After": str(decision.retry_after)},
        )
    try:
        result = AuthService(db).login(
            payload.username, payload.password, required_role="manager"
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_401_UNAUTHORIZED:
            rate_limiter.release(decision.reservation_id)
        raise
    # 成功登录后清除同一账号/IP 的历史失败记录。
    rate_limiter.clear(key)
    return result


@router.get("/me", response_model=UserResponse)
def manager_me(user: User = Depends(get_current_admin_or_manager)) -> UserResponse:
    """返回经理工作台当前账号；管理员可用于查看全局工作台。"""

    return user


@router.get("/stats", response_model=ManagerStats)
def get_manager_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin_or_manager),
):
    return ManagerService(db).stats(user)


@router.get("/subscriptions/{subscription_id}/preview", response_model=list[PreviewNode])
def preview_manager_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin_or_manager),
):
    manager_id = None if user.role == "admin" else user.id
    item = CustomerSubscriptionService(db).get(subscription_id, manager_id)
    if item is None:
        raise HTTPException(status_code=404, detail="客户订阅不存在")
    if user.role == "manager" and not is_effectively_active(item):
        raise HTTPException(status_code=404, detail="客户订阅已失效")
    return PackageService(db).preview(item.package)


@router.get(
    "/subscriptions/{subscription_id}/nodes/{node_id}/export",
    response_model=NodeExportResponse,
)
def export_manager_subscription_node(
    subscription_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin_or_manager),
) -> NodeExportResponse:
    """按客户订阅授权导出单个节点 URI；经理不能导出失效订阅节点。"""

    manager_id = None if user.role == "admin" else user.id
    item = CustomerSubscriptionService(db).get(subscription_id, manager_id)
    if item is None or (user.role == "manager" and not is_effectively_active(item)):
        raise HTTPException(status_code=404, detail="客户订阅不存在或已失效")
    preview = next((node for node in PackageService(db).preview(item.package) if node.id == node_id), None)
    node = NodeRepository(db).get(node_id)
    if preview is None or node is None:
        raise HTTPException(status_code=404, detail="该节点不属于当前订阅")
    content, node_count = export_nodes(
        [(node, preview.name)], "uri", subscription_name=item.package.subscription_name
    )
    if node_count != 1:
        raise HTTPException(status_code=400, detail="该节点缺少可导出字段或暂不支持分享")
    return NodeExportResponse(
        node_id=node.id,
        name=preview.name,
        type=node.type,
        format="uri",
        content=content.strip(),
    )
