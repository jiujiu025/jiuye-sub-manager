"""统一节点池接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.models.user import User
from app.repositories.node_repo import NodeRepository
from app.schemas.common import MessageResponse, Page
from app.schemas.node import (
    NodeBatchRequest,
    NodeCreate,
    NodeDetail,
    NodeImportRequest,
    NodeImportResult,
    NodeExportResponse,
    NodeSummary,
    NodeUpdate,
)
from app.schemas.node_health import NodeHealthResponse
from app.services.node_import_service import NodeImportService
from app.services.node_service import NodeService
from app.exporters import export_nodes

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=Page[NodeSummary])
def list_nodes(
    source_id: int | None = None,
    source_name: str | None = None,
    node_type: str | None = None,
    country: str | None = None,
    keyword: str | None = None,
    enabled: bool | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> Page[NodeSummary]:
    """分页查询统一节点池，支持来源/类型/地区/关键词筛选。"""

    safe_page = max(page, 1)
    safe_page_size = max(1, min(page_size, 100))
    items, total = NodeRepository(db).list_nodes(
        source_id=source_id,
        source_name=source_name,
        node_type=node_type,
        country=country,
        keyword=keyword,
        enabled=enabled,
        page=safe_page,
        page_size=safe_page_size,
    )
    return Page[NodeSummary](
        items=items,
        total=total,
        page=safe_page,
        page_size=safe_page_size,
    )


@router.post("/batch", response_model=MessageResponse)
def batch_nodes(
    payload: NodeBatchRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> MessageResponse:
    """批量启用/禁用/删除节点。"""

    processed = NodeService(db).batch(payload.ids, payload.action, admin)
    return MessageResponse(detail=f"已处理 {processed} 个节点")


@router.post("/import", response_model=NodeImportResult)
def import_nodes(
    payload: NodeImportRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> NodeImportResult:
    """批量导入节点链接或配置内容到统一节点池。"""

    return NodeImportService(db).import_content(
        payload.content,
        payload.source_subtype,
        payload.format,
        admin,
    )


@router.post("", response_model=NodeDetail, status_code=status.HTTP_201_CREATED)
def create_self_node(
    payload: NodeCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> NodeDetail:
    """添加自有 VLESS/SS 节点。"""

    return NodeService(db).create(payload, admin)


@router.get("/{node_id}/health", response_model=NodeHealthResponse)
def get_node_health(
    node_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> NodeHealthResponse:
    """返回节点健康状态接口；未启用探测前统一为 unknown。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    return NodeHealthResponse(node_id=node.id, status="unknown")


@router.get("/{node_id}/export", response_model=NodeExportResponse)
def export_node(
    node_id: int,
    format: str = Query(default="uri"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> NodeExportResponse:
    """导出单个节点的标准分享链接。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    output_format = format.strip().lower()
    if output_format != "uri":
        raise HTTPException(status_code=400, detail="单节点分享目前仅支持 URI 格式")
    content, node_count = export_nodes([(node, node.name)], output_format)
    if node_count != 1:
        raise HTTPException(status_code=400, detail="该节点缺少可导出字段或暂不支持分享")
    return NodeExportResponse(
        node_id=node.id,
        name=node.name,
        type=node.type,
        format=output_format,
        content=content.strip(),
    )


@router.get("/{node_id}", response_model=NodeDetail)
def get_node(
    node_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """获取节点详情。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    return node


@router.put("/{node_id}", response_model=NodeDetail)
def update_node(
    node_id: int,
    payload: NodeUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """修改节点。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    return NodeService(db).update(node, payload, admin)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(
    node_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> None:
    """删除节点。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    NodeService(db).delete(node, admin)
