"""外部通知设置与投递测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.notification import Notification
from app.models.user import User
from app.services import notification_delivery_service as delivery_module
from app.services.notification_delivery_service import NotificationDeliveryService


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_notification_secrets_are_not_returned(
    client: TestClient,
) -> None:
    """设置接口只返回配置状态和脱敏接收人。"""

    headers = _admin_headers(client)
    response = client.put(
        "/api/system/settings",
        headers=headers,
        json={
            "telegram_enabled": True,
            "telegram_bot_token": "bot-secret-value",
            "telegram_chat_ids": ["123456789"],
            "wechat_enabled": True,
            "wechat_app_id": "wx-app-id",
            "wechat_app_secret": "wechat-app-secret",
            "wechat_template_id": "template-id",
            "wechat_openids": ["openid-secret-value"],
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "bot-secret-value" not in body
    assert "wechat-app-secret" not in body
    assert response.json()["telegram_configured"] is True
    assert response.json()["wechat_configured"] is True

    clear = client.put(
        "/api/system/settings",
        headers=headers,
        json={"clear_telegram_config": True, "clear_wechat_config": True},
    )
    assert clear.status_code == 200
    assert clear.json()["telegram_configured"] is False
    assert clear.json()["wechat_configured"] is False


def test_notification_delivery_marks_success_without_duplicate_channel_send(
    client: TestClient,
    monkeypatch,
) -> None:
    """一个渠道成功后，另一个渠道失败重试不会重复成功渠道。"""

    calls: list[str] = []

    class FakeResponse:
        status_code = 200

        def __init__(self, data: dict) -> None:
            self._data = data

        def json(self) -> dict:
            return self._data

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def post(self, url: str, **_kwargs):
            calls.append(url)
            if "telegram.org" in url:
                return FakeResponse({"ok": True})
            return FakeResponse({"errcode": 40001})

        def get(self, *_args, **_kwargs):
            return FakeResponse({"errcode": 40001})

    monkeypatch.setattr(delivery_module.httpx, "Client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(
        delivery_module.SettingsService,
        "get_notification_config",
        lambda _self: {
            "telegram_enabled": True,
            "telegram_bot_token": "bot",
            "telegram_chat_ids": ["123"],
            "wechat_enabled": True,
            "wechat_app_id": "app",
            "wechat_app_secret": "secret",
            "wechat_template_id": "template",
            "wechat_openids": ["openid"],
        },
    )

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.role == "admin"))
        assert user is not None
        # 测试库使用 create_all，不经过迁移中的历史通知 skipped 初始化。
        for existing in db.scalars(select(Notification)).all():
            existing.telegram_push_status = "skipped"
            existing.wechat_push_status = "skipped"
        db.commit()
        notification = Notification(
            recipient_user_id=user.id,
            kind="system",
            priority="normal",
            dedupe_key="delivery-test",
            title="测试通知",
            content="测试内容",
        )
        db.add(notification)
        db.commit()
        service = NotificationDeliveryService(db)
        assert service.dispatch_pending() == 1
        db.refresh(notification)
        assert notification.telegram_push_status == "sent"
        assert notification.wechat_push_status == "failed"
        assert notification.external_push_attempts == 1
        assert sum("telegram.org" in call for call in calls) == 1
