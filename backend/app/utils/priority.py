"""来源去重优先级工具。"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.models.setting import SystemSetting
from app.repositories.source_repo import SourceRepository

logger = logging.getLogger(__name__)

# 自有节点的统一来源名称
SELF_SOURCE_NAME = "自有节点"


def build_source_priority(db: Session) -> dict[str, int]:
    """构建来源优先级映射：数值越小优先级越高，自有节点恒为最高。"""

    priority: dict[str, int] = {SELF_SOURCE_NAME: 0}
    next_index = 1

    setting = db.get(SystemSetting, "dedup_source_priority")
    configured: list[str] = []
    if setting is not None:
        try:
            parsed = json.loads(setting.value or "[]")
            configured = [item for item in parsed if isinstance(item, str)]
        except json.JSONDecodeError:
            logger.warning("dedup_source_priority 配置不是合法 JSON，已忽略")

    for name in configured:
        if name not in priority:
            priority[name] = next_index
            next_index += 1

    # 未显式配置的来源按创建顺序排在后面
    for source in SourceRepository(db).list():
        if source.name not in priority:
            priority[source.name] = next_index
            next_index += 1

    return priority
