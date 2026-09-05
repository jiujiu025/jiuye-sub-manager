"""ORM 基类与通用工具。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """返回当前 UTC 时间，供时间字段默认值使用。"""

    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。"""
