"""站内通知的 Telegram 与微信公众号投递。"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5
_wechat_access_tokens: dict[str, tuple[str, float]] = {}


class NotificationDeliveryError(RuntimeError):
    """外部通知渠道返回失败。"""


class NotificationDeliveryService:
    """异步感知的投递服务，实际由 APScheduler 每分钟调用。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def dispatch_pending(self, limit: int = 100) -> int:
        """投递待处理通知，并让单个渠道失败不影响另一个渠道。"""

        config = SettingsService(self.db).get_notification_config()
        rows = list(
            self.db.scalars(
                select(Notification)
                .where(
                    or_(
                        Notification.telegram_push_status.in_(["pending", "failed"]),
                        Notification.wechat_push_status.in_(["pending", "failed"]),
                    ),
                    Notification.external_push_attempts < _MAX_ATTEMPTS,
                )
                .order_by(Notification.created_at.asc(), Notification.id.asc())
                .limit(limit)
            ).all()
        )
        if not rows:
            return 0

        processed = 0
        with httpx.Client(timeout=10, trust_env=False) as client:
            for notification in rows:
                notification.external_push_attempts += 1
                notification.external_last_attempt_at = datetime.now(timezone.utc)
                self.db.commit()
                self._dispatch_one(notification, config, client)
                self.db.commit()
                processed += 1
        return processed

    def send_test(self, channel: str, content: str) -> int:
        """向指定渠道发送一条测试消息，不创建站内通知记录。"""

        config = SettingsService(self.db).get_notification_config()
        with httpx.Client(timeout=10, trust_env=False) as client:
            if channel == "telegram":
                if not config["telegram_enabled"]:
                    raise NotificationDeliveryError("Telegram 渠道未启用")
                self._send_telegram(
                    client,
                    config["telegram_bot_token"],
                    config["telegram_chat_ids"],
                    content,
                )
                return len(config["telegram_chat_ids"])
            if channel == "wechat":
                if not config["wechat_enabled"]:
                    raise NotificationDeliveryError("微信公众号渠道未启用")
                if not all(
                    config[key]
                    for key in (
                        "wechat_app_id",
                        "wechat_app_secret",
                        "wechat_template_id",
                        "wechat_openids",
                    )
                ):
                    raise NotificationDeliveryError("微信公众号配置不完整")
                access_token = self._wechat_access_token(
                    client,
                    config["wechat_app_id"],
                    config["wechat_app_secret"],
                )
                for openid in config["wechat_openids"]:
                    self._send_wechat(
                        client,
                        access_token,
                        config["wechat_template_id"],
                        openid,
                        "通知测试",
                        content,
                    )
                return len(config["wechat_openids"])
        raise NotificationDeliveryError("不支持的通知渠道")

    def _dispatch_one(self, notification: Notification, config: dict, client: httpx.Client) -> None:
        """分别处理渠道状态，已成功渠道不会因为另一渠道失败而重复发送。"""

        if notification.telegram_push_status in {"pending", "failed"}:
            if not config["telegram_enabled"]:
                notification.telegram_push_status = "skipped"
            elif not config["telegram_bot_token"] or not config["telegram_chat_ids"]:
                self._failed(notification, "telegram", "Telegram 配置不完整")
            else:
                delivered = self._delivered_values(notification.telegram_delivered_chat_ids)
                failed_message = None
                for chat_id in config["telegram_chat_ids"]:
                    if chat_id in delivered:
                        continue
                    try:
                        self._send_telegram(
                            client,
                            config["telegram_bot_token"],
                            [chat_id],
                            self._format_content(notification),
                        )
                    except NotificationDeliveryError as exc:
                        failed_message = str(exc)
                        continue
                    delivered.add(chat_id)
                notification.telegram_delivered_chat_ids = sorted(delivered)
                if failed_message:
                    self._failed(notification, "telegram", failed_message)
                else:
                    notification.telegram_push_status = "sent"
                    notification.telegram_push_error = None
                    notification.telegram_pushed_at = datetime.now(timezone.utc)

        if notification.wechat_push_status in {"pending", "failed"}:
            if not config["wechat_enabled"]:
                notification.wechat_push_status = "skipped"
            elif not all(
                config[key]
                for key in (
                    "wechat_app_id",
                    "wechat_app_secret",
                    "wechat_template_id",
                    "wechat_openids",
                )
            ):
                self._failed(notification, "wechat", "微信公众号配置不完整")
            else:
                delivered = self._delivered_values(notification.wechat_delivered_openids)
                try:
                    access_token = self._wechat_access_token(
                        client,
                        config["wechat_app_id"],
                        config["wechat_app_secret"],
                    )
                    failed_message = None
                    for openid in config["wechat_openids"]:
                        if openid in delivered:
                            continue
                        self._send_wechat(
                            client,
                            access_token,
                            config["wechat_template_id"],
                            openid,
                            notification.title,
                            notification.content,
                        )
                        delivered.add(openid)
                    notification.wechat_delivered_openids = sorted(delivered)
                except NotificationDeliveryError as exc:
                    failed_message = str(exc)
                    notification.wechat_delivered_openids = sorted(delivered)
                    self._failed(notification, "wechat", failed_message)
                else:
                    failed_message = None
                if failed_message is None:
                    notification.wechat_push_status = "sent"
                    notification.wechat_push_error = None
                    notification.wechat_pushed_at = datetime.now(timezone.utc)

    @staticmethod
    def _delivered_values(value: list | None) -> set[str]:
        """读取已成功投递的接收人列表，过滤异常结构。"""

        if not isinstance(value, list):
            return set()
        return {str(item) for item in value if str(item).strip()}

    @staticmethod
    def _failed(notification: Notification, channel: str, message: str) -> None:
        setattr(notification, f"{channel}_push_status", "failed")
        setattr(notification, f"{channel}_push_error", message[:240])

    @staticmethod
    def _format_content(notification: Notification) -> str:
        return f"【{notification.title}】\n{notification.content}"

    @staticmethod
    def _send_telegram(
        client: httpx.Client,
        bot_token: str,
        chat_ids: list[str],
        content: str,
    ) -> None:
        if not bot_token or not chat_ids:
            raise NotificationDeliveryError("Telegram 配置不完整")
        for chat_id in chat_ids:
            try:
                response = client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": content},
                )
                data = response.json()
            except (httpx.HTTPError, ValueError):
                raise NotificationDeliveryError("Telegram 请求失败") from None
            if response.status_code >= 400 or not data.get("ok"):
                raise NotificationDeliveryError("Telegram 接口拒绝了消息")

    @classmethod
    def _wechat_access_token(
        cls,
        client: httpx.Client,
        app_id: str,
        app_secret: str,
    ) -> str:
        cached = _wechat_access_tokens.get(app_id)
        if cached and cached[1] > time.time():
            return cached[0]
        try:
            response = client.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": app_id,
                    "secret": app_secret,
                },
            )
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise NotificationDeliveryError("微信公众号 access_token 请求失败") from None
        if response.status_code >= 400 or data.get("errcode", 0) != 0 or not data.get("access_token"):
            raise NotificationDeliveryError(
                f"微信公众号 access_token 获取失败（错误码 {data.get('errcode', 'unknown')}）"
            )
        token = str(data["access_token"])
        _wechat_access_tokens[app_id] = (token, time.time() + max(60, int(data.get("expires_in", 7200)) - 300))
        return token

    @staticmethod
    def _send_wechat(
        client: httpx.Client,
        access_token: str,
        template_id: str,
        openid: str,
        title: str,
        content: str,
    ) -> None:
        try:
            response = client.post(
                "https://api.weixin.qq.com/cgi-bin/message/template/send",
                params={"access_token": access_token},
                json={
                    "touser": openid,
                    "template_id": template_id,
                    "data": {
                        "first": {"value": title},
                        "keyword1": {"value": content[:200]},
                        "remark": {"value": "Sub-Manager 通知中心"},
                    },
                },
            )
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise NotificationDeliveryError("微信公众号模板消息请求失败") from None
        if response.status_code >= 400 or data.get("errcode", 0) != 0:
            raise NotificationDeliveryError(
                f"微信公众号模板消息发送失败（错误码 {data.get('errcode', 'unknown')}）"
            )
