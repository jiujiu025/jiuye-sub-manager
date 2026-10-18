"""地区识别接口模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CountryResolveRequest(BaseModel):
    """管理员手动触发地区识别请求。"""

    ids: list[int] | None = Field(default=None, min_length=1, max_length=500)
    limit: int = Field(default=100, ge=1, le=500)
    force: bool = False


class CountryResolveResponse(BaseModel):
    """地区识别统计。"""

    processed: int
    resolved: int
    name_resolved: int
    cached: int
    skipped: int
    failed: int
    remaining: bool
    errors: list[str]
