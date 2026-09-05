"""系统设置业务逻辑：运行时设置优先于环境变量默认值。"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.core.cache import cache_service
from app.core.config import get_settings
from app.repositories.setting_repo import SystemSettingRepository
from app.schemas.settings import SystemSettingsResponse, SystemSettingsUpdate

logger = logging.getLogger(__name__)


class SettingsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SystemSettingRepository(db)

    def get(self) -> SystemSettingsResponse:
        defaults = get_settings()
        return SystemSettingsResponse(
            sync_interval_minutes=self._int_value(
                "sync_interval_minutes", defaults.sync_interval_minutes
            ),
            sync_enabled=self._bool_value("sync_enabled", defaults.sync_enabled),
            cache_ttl_seconds=self._int_value(
                "cache_ttl_seconds", defaults.cache_ttl_seconds
            ),
            dedup_source_priority=self._list_value("dedup_source_priority"),
        )

    def apply(self, payload: SystemSettingsUpdate) -> SystemSettingsResponse:
        data = payload.model_dump(exclude_unset=True)
        if "sync_interval_minutes" in data:
            self.repo.set("sync_interval_minutes", str(data["sync_interval_minutes"]))
        if "sync_enabled" in data:
            self.repo.set("sync_enabled", "true" if data["sync_enabled"] else "false")
        if "cache_ttl_seconds" in data:
            self.repo.set("cache_ttl_seconds", str(data["cache_ttl_seconds"]))
            cache_service.reconfigure(data["cache_ttl_seconds"])
        if "dedup_source_priority" in data:
            self.repo.set(
                "dedup_source_priority",
                json.dumps(list(data["dedup_source_priority"]), ensure_ascii=False),
            )
        self.db.commit()
        return self.get()

    def _int_value(self, key: str, default: int) -> int:
        setting = self.repo.get(key)
        if setting is None:
            return default
        try:
            return int(setting.value)
        except ValueError:
            logger.warning("系统设置 %s 不是合法整数，使用默认值", key)
            return default

    def _bool_value(self, key: str, default: bool) -> bool:
        setting = self.repo.get(key)
        if setting is None:
            return default
        return setting.value.strip().lower() in ("1", "true", "yes", "on")

    def _list_value(self, key: str) -> list[str]:
        setting = self.repo.get(key)
        if setting is None:
            return []
        try:
            parsed = json.loads(setting.value or "[]")
            return [item for item in parsed if isinstance(item, str)]
        except json.JSONDecodeError:
            logger.warning("系统设置 %s 不是合法 JSON，返回空列表", key)
            return []
