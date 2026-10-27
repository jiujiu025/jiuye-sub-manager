"""节点健康状态接口模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

NodeHealthStatus = Literal["healthy", "degraded", "offline", "unknown"]


class NodeHealthResponse(BaseModel):
    """节点健康状态和最近一次探测结果。"""

    node_id: int
    status: NodeHealthStatus
    checked_at: datetime | None = None
    latency_ms: int | None = None
    detail: str | None = None
    tcp_status: str = "unknown"
    tls_status: str = "unknown"
    tcp_latency_ms: int | None = None
    tls_latency_ms: int | None = None
    udp_status: str = "unknown"
    udp_latency_ms: int | None = None


class NodeHealthBatchResponse(BaseModel):
    """手动批量健康检测结果。"""

    checked: int


class NodeHealthSettings(BaseModel):
    """节点健康检测的运行时设置。"""

    health_enabled: bool
    health_interval_minutes: int
    health_timeout_seconds: float
    health_failure_threshold: int
    health_recovery_threshold: int
    health_probe_concurrency: int
