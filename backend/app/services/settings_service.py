"""系统设置业务逻辑：运行时设置优先于环境变量默认值。"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.cache import cache_service
from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.repositories.setting_repo import SystemSettingRepository
from app.schemas.settings import SystemSettingsResponse, SystemSettingsUpdate

logger = logging.getLogger(__name__)


class SettingsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SystemSettingRepository(db)

    def get(self) -> SystemSettingsResponse:
        defaults = get_settings()
        notification = self.get_notification_config()
        return SystemSettingsResponse(
            sync_interval_minutes=self._int_value(
                "sync_interval_minutes", defaults.sync_interval_minutes
            ),
            sync_enabled=self._bool_value("sync_enabled", defaults.sync_enabled),
            cache_ttl_seconds=self._int_value(
                "cache_ttl_seconds", defaults.cache_ttl_seconds
            ),
            dedup_source_priority=self._list_value("dedup_source_priority"),
            health_enabled=self._bool_value("health_enabled", True),
            health_interval_minutes=self._int_value(
                "health_interval_minutes", 5
            ),
            health_timeout_seconds=self._float_value(
                "health_timeout_seconds", defaults.health_timeout_seconds
            ),
            health_failure_threshold=self._int_value("health_failure_threshold", 3),
            health_recovery_threshold=self._int_value("health_recovery_threshold", 2),
            health_probe_concurrency=self._int_value(
                "health_probe_concurrency", defaults.health_probe_concurrency
            ),
            health_probe_mode=self._mode_value(
                "health_probe_mode", defaults.health_probe_mode
            ),
            telegram_enabled=notification["telegram_enabled"],
            telegram_configured=bool(
                notification["telegram_bot_token"] and notification["telegram_chat_ids"]
            ),
            telegram_chat_ids_masked=[
                mask_secret(item, keep_head=2, keep_tail=2)
                for item in notification["telegram_chat_ids"]
            ],
            wechat_enabled=notification["wechat_enabled"],
            wechat_configured=bool(
                notification["wechat_app_id"]
                and notification["wechat_app_secret"]
                and notification["wechat_template_id"]
                and notification["wechat_openids"]
            ),
            wechat_openids_masked=[
                mask_secret(item, keep_head=3, keep_tail=3)
                for item in notification["wechat_openids"]
            ],
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
        for key in (
            "health_enabled",
            "health_interval_minutes",
            "health_timeout_seconds",
            "health_failure_threshold",
            "health_recovery_threshold",
            "health_probe_concurrency",
            "health_probe_mode",
        ):
            if key in data:
                self.repo.set(key, str(data[key]).lower() if isinstance(data[key], bool) else str(data[key]))
        self._apply_notification_settings(data)
        self.db.commit()
        return self.get()

    def get_notification_config(self) -> dict[str, Any]:
        """读取外部通知配置；密钥只在后端投递时解密使用。"""

        defaults = get_settings()
        telegram_token = self._secret_value(
            "notification_telegram_bot_token", defaults.telegram_bot_token
        )
        telegram_chat_ids = self._list_secret_value(
            "notification_telegram_chat_ids",
            self._split_values(defaults.telegram_chat_id),
        )
        telegram_enabled = self._bool_value(
            "notification_telegram_enabled",
            bool(telegram_token and telegram_chat_ids),
        )
        wechat_app_id = self._secret_value("notification_wechat_app_id", "")
        wechat_app_secret = self._secret_value("notification_wechat_app_secret", "")
        wechat_template_id = self._secret_value("notification_wechat_template_id", "")
        wechat_openids = self._list_secret_value("notification_wechat_openids", [])
        wechat_enabled = self._bool_value(
            "notification_wechat_enabled",
            bool(wechat_app_id and wechat_app_secret and wechat_template_id and wechat_openids),
        )
        return {
            "telegram_enabled": telegram_enabled,
            "telegram_bot_token": telegram_token,
            "telegram_chat_ids": telegram_chat_ids,
            "wechat_enabled": wechat_enabled,
            "wechat_app_id": wechat_app_id,
            "wechat_app_secret": wechat_app_secret,
            "wechat_template_id": wechat_template_id,
            "wechat_openids": wechat_openids,
        }

    def _apply_notification_settings(self, data: dict[str, Any]) -> None:
        """保存外部通知设置，空密钥不会覆盖已有密钥。"""

        if data.get("clear_telegram_config"):
            # 用加密空值覆盖环境变量兜底，确保后台明确清除后不会被旧环境配置重新启用。
            self.repo.set("notification_telegram_bot_token", encrypt_secret(""))
            self.repo.set("notification_telegram_chat_ids", encrypt_secret("[]"))
            self.repo.set("notification_telegram_enabled", "false")
        else:
            if data.get("telegram_enabled") is not None:
                self.repo.set(
                    "notification_telegram_enabled",
                    "true" if data["telegram_enabled"] else "false",
                )
            if data.get("telegram_bot_token"):
                self.repo.set(
                    "notification_telegram_bot_token",
                    encrypt_secret(data["telegram_bot_token"].strip()),
                )
            if data.get("telegram_chat_ids") is not None:
                values = self._clean_values(data["telegram_chat_ids"])
                self.repo.set(
                    "notification_telegram_chat_ids",
                    encrypt_secret(json.dumps(values, ensure_ascii=False)),
                )

        if data.get("clear_wechat_config"):
            self.repo.set("notification_wechat_app_id", encrypt_secret(""))
            self.repo.set("notification_wechat_app_secret", encrypt_secret(""))
            self.repo.set("notification_wechat_template_id", encrypt_secret(""))
            self.repo.set("notification_wechat_openids", encrypt_secret("[]"))
            self.repo.set("notification_wechat_enabled", "false")
        else:
            if data.get("wechat_enabled") is not None:
                self.repo.set(
                    "notification_wechat_enabled",
                    "true" if data["wechat_enabled"] else "false",
                )
            for field, key in (
                ("wechat_app_id", "notification_wechat_app_id"),
                ("wechat_app_secret", "notification_wechat_app_secret"),
                ("wechat_template_id", "notification_wechat_template_id"),
            ):
                if data.get(field):
                    self.repo.set(key, encrypt_secret(data[field].strip()))
            if data.get("wechat_openids") is not None:
                values = self._clean_values(data["wechat_openids"])
                self.repo.set(
                    "notification_wechat_openids",
                    encrypt_secret(json.dumps(values, ensure_ascii=False)),
                )

    def _secret_value(self, key: str, fallback: str) -> str:
        setting = self.repo.get(key)
        if setting is None or not setting.value:
            return fallback.strip()
        try:
            return decrypt_secret(setting.value)
        except Exception:
            logger.warning("系统设置 %s 解密失败，忽略该配置", key)
            return ""

    def _list_secret_value(self, key: str, fallback: list[str]) -> list[str]:
        raw = self._secret_value(key, "")
        if not raw:
            return fallback
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return self._split_values(raw)
        return self._clean_values(value) if isinstance(value, list) else []

    @staticmethod
    def _split_values(value: str) -> list[str]:
        return [item.strip() for item in value.replace(",", "\n").splitlines() if item.strip()]

    @staticmethod
    def _clean_values(values: list[Any]) -> list[str]:
        return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))

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

    def _float_value(self, key: str, default: float) -> float:
        setting = self.repo.get(key)
        if setting is None:
            return default
        try:
            return float(setting.value)
        except ValueError:
            logger.warning("系统设置 %s 不是合法数字，使用默认值", key)
            return default

    def _mode_value(self, key: str, default: str) -> str:
        setting = self.repo.get(key)
        if setting is None or setting.value not in {"full", "basic"}:
            return default if default in {"full", "basic"} else "full"
        return setting.value

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
