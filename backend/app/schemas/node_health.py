"""节点健康状态接口模型；本轮只定义状态，不主动探测节点。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

NodeHealthStatus = Literal["healthy", "degraded", "offline", "unknown"]


class NodeHealthResponse(BaseModel):
    """节点健康状态，为后续探测器保留稳定 API。"""

    node_id: int
    status: NodeHealthStatus
    checked_at: datetime | None = None
    detail: str | None = None
