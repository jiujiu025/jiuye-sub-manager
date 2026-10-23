"""统一节点池接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.models.user import User
from app.models.three_xui import ForwardedNodeMapping, ThreeXUIServer
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
    NodeUsageResponse,
)
from app.schemas.node_health import NodeHealthBatchResponse, NodeHealthResponse
from app.schemas.geo import CountryResolveRequest, CountryResolveResponse
from app.services.node_import_service import NodeImportService
from app.services.node_service import NodeService
from app.services.node_health_service import NodeHealthService
from app.services.geoip_service import GeoIPService
from app.exporters import export_nodes

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=Page[NodeSummary])
def list_nodes(
    source_id: int | None = None,
    source_kind: Literal["subscription", "custom", "external", "forwarded"] | None = None,
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
        source_kind=source_kind,
        source_name=source_name,
        node_type=node_type,
        country=country,
        keyword=keyword,
        enabled=enabled,
        page=safe_page,
        page_size=safe_page_size,
    )
    _attach_forwarding_summaries(db, items)
    return Page[NodeSummary](
        items=items,
        total=total,
        page=safe_page,
        page_size=safe_page_size,
    )


def _attach_forwarding_summaries(db: Session, nodes: list) -> None:
    """为资源池列表补充转发元数据，不把完整链接或凭证放入列表响应。"""

    forwarded_ids = [node.id for node in nodes if node.node_category == "forwarded"]
    if not forwarded_ids:
        return
    rows = db.execute(
        select(ForwardedNodeMapping, ThreeXUIServer)
        .join(ThreeXUIServer, ThreeXUIServer.id == ForwardedNodeMapping.target_server_id)
        .where(ForwardedNodeMapping.forwarded_node_id.in_(forwarded_ids))
    ).all()
    mapping_by_node = {mapping.forwarded_node_id: (mapping, server) for mapping, server in rows}
    for node in nodes:
        mapping_server = mapping_by_node.get(node.id)
        if mapping_server is None:
            continue
        mapping, server = mapping_server
        setattr(node, "forward_target_server_name", server.name)
        setattr(node, "forward_target_server_address", server.domain or server.ip)
        setattr(node, "forward_inbound_id", mapping.inbound_id)
        setattr(node, "forward_inbound_remark", mapping.inbound_remark)
        # 这是可复制链接的非敏感端点摘要，完整链接仍通过 /export 按需获取。
        setattr(node, "forward_inbound_endpoint", f"{node.server}:{node.port}")
        setattr(node, "forward_status", mapping.status)
        setattr(node, "forwarded_from_node_id", mapping.source_node_id)


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
    """批量导入外部节点链接或配置内容到统一资源池。"""

    return NodeImportService(db).import_content(
        payload.content,
        payload.source_subtype,
        payload.format,
        admin,
        payload.note,
        payload.expires_at,
    )


@router.post("/country/resolve", response_model=CountryResolveResponse)
def resolve_node_countries(
    payload: CountryResolveRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> CountryResolveResponse:
    """批量补全资源池中缺失的地区；外部接口失败只记录失败统计。"""

    service = GeoIPService(db)
    try:
        return CountryResolveResponse(**service.resolve_nodes(
            node_ids=payload.ids,
            limit=payload.limit,
            force=payload.force,
        ))
    finally:
        service.close()


@router.post("/{node_id}/country/resolve", response_model=CountryResolveResponse)
def resolve_node_country(
    node_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> CountryResolveResponse:
    """补全单个节点地区，便于管理员排查域名或特殊线路。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    service = GeoIPService(db)
    try:
        status_value, detail = service.resolve_node(node, force=force)
        db.commit()
        return CountryResolveResponse(
            processed=1,
            resolved=1 if status_value == "resolved" else 0,
            name_resolved=1 if detail == "name" else 0,
            cached=1 if detail == "cache" else 0,
            skipped=1 if status_value == "skipped" else 0,
            failed=1 if status_value == "failed" else 0,
            remaining=False,
            errors=[detail] if status_value == "failed" and detail else [],
        )
    finally:
        service.close()


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
    """返回节点最近一次健康探测结果。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    return NodeHealthResponse(
        node_id=node.id,
        status=node.health_status,
        checked_at=node.health_checked_at,
        latency_ms=node.health_latency_ms,
        detail=node.health_detail,
        tcp_status=node.health_tcp_status,
        tls_status=node.health_tls_status,
        tcp_latency_ms=node.health_tcp_latency_ms,
        tls_latency_ms=node.health_tls_latency_ms,
    )


@router.post("/{node_id}/health/check", response_model=NodeHealthResponse)
def check_node_health(
    node_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> NodeHealthResponse:
    """立即探测单个节点，便于导入后确认线路。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    checked = NodeHealthService(db).run_node(node)
    return NodeHealthResponse(
        node_id=checked.id,
        status=checked.health_status,
        checked_at=checked.health_checked_at,
        latency_ms=checked.health_latency_ms,
        detail=checked.health_detail,
        tcp_status=checked.health_tcp_status,
        tls_status=checked.health_tls_status,
        tcp_latency_ms=checked.health_tcp_latency_ms,
        tls_latency_ms=checked.health_tls_latency_ms,
    )


@router.post("/health/check-all", response_model=NodeHealthBatchResponse)
def check_all_node_health(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> NodeHealthBatchResponse:
    """手动检测全部启用节点，包含上游订阅、外部导入和已转发节点。"""

    checked = NodeHealthService(db).run_all(include_all=True)
    return NodeHealthBatchResponse(checked=checked)


@router.get("/{node_id}/usage", response_model=NodeUsageResponse)
def get_node_usage(
    node_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> NodeUsageResponse:
    """查看节点被套餐和客户订阅使用的范围。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    return NodeService(db).usage(node)


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
) -> Response:
    """删除节点。"""

    node = NodeRepository(db).get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    NodeService(db).delete(node, admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
