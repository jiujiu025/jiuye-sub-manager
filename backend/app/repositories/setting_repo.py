"""系统键值设置数据访问。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.setting import SystemSetting


class SystemSettingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, key: str) -> SystemSetting | None:
        return self.db.get(SystemSetting, key)

    def set(self, key: str, value: str) -> SystemSetting:
        setting = self.get(key)
        if setting is None:
            setting = SystemSetting(key=key, value=value)
            self.db.add(setting)
        else:
            setting.value = value
        return setting
