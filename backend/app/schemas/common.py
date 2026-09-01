"""通用响应模型。"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    """允许直接从 ORM 对象构造响应。"""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """统一分页响应。"""

    items: list[T]
    total: int
    page: int
    page_size: int


class MessageResponse(BaseModel):
    """通用消息响应。"""

    detail: str
