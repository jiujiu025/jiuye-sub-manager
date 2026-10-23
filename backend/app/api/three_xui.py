"""3x-ui 服务器和转发任务管理员接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.models.three_xui import ForwardTask, ForwardedNodeMapping, ThreeXUIServer
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.three_xui import (
    ForwardBatchCreate,
    ForwardBatchResponse,
    ForwardTaskCreate,
    ForwardTaskSummary,
    ForwardedNodeMappingSummary,
    ThreeXUIServerCheckResponse,
    ThreeXUIServerCreate,
    ThreeXUIServerSummary,
    ThreeXUIServerUpdate,
    ThreeXUIInboundTestCreate,
    ThreeXUIInboundTestResponse,
)
from app.services.three_xui_service import ThreeXUIService

router = APIRouter(prefix="/three-xui", tags=["three-xui"])


@router.get("/servers", response_model=list[ThreeXUIServerSummary])
def list_servers(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[ThreeXUIServer]:
    """列出服务器摘要，永远不返回 API Token 明文。"""

    return ThreeXUIService(db).list_servers()


@router.post(
    "/servers",
    response_model=ThreeXUIServerSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_server(
    payload: ThreeXUIServerCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ThreeXUIServer:
    return ThreeXUIService(db).create_server(payload, admin)


@router.put("/servers/{server_id}", response_model=ThreeXUIServerSummary)
def update_server(
    server_id: int,
    payload: ThreeXUIServerUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ThreeXUIServer:
    service = ThreeXUIService(db)
    server = service.get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="3x-ui 服务器不存在")
    return service.update_server(server, payload, admin)


@router.post("/servers/{server_id}/check", response_model=ThreeXUIServerCheckResponse)
def check_server(
    server_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ThreeXUIServerCheckResponse:
    service = ThreeXUIService(db)
    server = service.get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="3x-ui 服务器不存在")
    result, count, message = service.check_server(server, admin)
    return ThreeXUIServerCheckResponse(
        server_id=server.id,
        status=result,
        checked_at=server.last_api_check_at,
        message=message,
        inbound_count=count,
    )


@router.post(
    "/servers/{server_id}/inbounds/test",
    response_model=ThreeXUIInboundTestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_test_inbound(
    server_id: int,
    payload: ThreeXUIInboundTestCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ThreeXUIInboundTestResponse:
    """直接调用 3x-ui 新增测试入站，便于定位转发失败环节。"""

    service = ThreeXUIService(db)
    server = service.get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="3x-ui 服务器不存在")
    return service.create_test_inbound(server, payload, admin)


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_server(
    server_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    service = ThreeXUIService(db)
    server = service.get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="3x-ui 服务器不存在")
    service.delete_server(server, admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tasks", response_model=list[ForwardTaskSummary])
def list_tasks(
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[ForwardTask]:
    return ThreeXUIService(db).list_tasks(limit)


@router.get("/tasks/{task_id}", response_model=ForwardTaskSummary)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ForwardTask:
    task = db.get(ForwardTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="转发任务不存在")
    return task


@router.post("/forward", response_model=ForwardTaskSummary, status_code=status.HTTP_202_ACCEPTED)
def create_forward_task(
    payload: ForwardTaskCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ForwardTask:
    """创建异步转发任务，不在请求线程调用目标面板。"""

    return ThreeXUIService(db).create_task(payload, admin)


@router.post(
    "/forward/batch",
    response_model=ForwardBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_forward_batch(
    payload: ForwardBatchCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ForwardBatchResponse:
    """批量创建独立转发任务，端口由后台按范围分配。"""

    return ThreeXUIService(db).create_batch(payload, admin)


@router.post("/tasks/{task_id}/retry", response_model=ForwardTaskSummary)
def retry_forward_task(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ForwardTask:
    task = db.get(ForwardTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="转发任务不存在")
    return ThreeXUIService(db).retry_task(task)


@router.get("/mappings", response_model=list[ForwardedNodeMappingSummary])
def list_mappings(
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[ForwardedNodeMapping]:
    return ThreeXUIService(db).list_mappings(limit)


@router.post("/mappings/{mapping_id}/cleanup", response_model=MessageResponse)
def cleanup_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> MessageResponse:
    mapping = db.get(ForwardedNodeMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="转发映射不存在")
    ThreeXUIService(db).cleanup_mapping(mapping, admin)
    return MessageResponse(detail="远端转发资源已清理")
