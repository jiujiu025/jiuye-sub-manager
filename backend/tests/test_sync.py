"""上游同步业务测试：成功、失败保留旧节点、空订阅策略、事务性。"""

from __future__ import annotations

import base64

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models.log import SyncLog
from app.models.source import Source
from app.repositories.node_repo import NodeRepository
from app.services.sync_service import SyncService


def _valid_subscription(tag: str = "a") -> str:
    lines = [
        f"vless://uuid-{tag}@hk-{tag}.example.com:443?security=reality&sni=hk-{tag}.example.com#%E9%A6%99%E6%B8%AF01",
        f"vless://uuid-{tag}-jp@jp-{tag}.example.com:443?security=reality&sni=jp-{tag}.example.com#%E6%97%A5%E6%9C%AC01",
    ]
    return base64.b64encode("\n".join(lines).encode("utf-8")).decode("ascii")


def _create_source(db, name: str = "airport_a") -> Source:
    source = Source(
        name=name,
        url="https://example.com/sub",
        enabled=True,
        allow_empty_override=False,
        format="auto",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5)


@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()


def _sync_logs(db, source_id: int) -> list[SyncLog]:
    stmt = (
        select(SyncLog)
        .where(SyncLog.source_id == source_id)
        .order_by(SyncLog.id)
    )
    return list(db.scalars(stmt).all())


def test_sync_success_writes_nodes_and_version(db_session) -> None:
    """成功同步应写入节点、更新版本并记录同步日志。"""

    source = _create_source(db_session)
    client = _mock_client(lambda request: httpx.Response(200, text=_valid_subscription()))
    result = SyncService(db_session, http_client=client).sync_source(source)

    assert result.status == "success"
    assert result.node_count == 2
    assert result.added_count == 2
    assert result.removed_count == 0

    db_session.refresh(source)
    assert source.node_count == 2
    assert source.version == 1
    assert source.last_sync_status == "success"
    assert NodeRepository(db_session).count_by_source(source.id) == 2
    assert len(_sync_logs(db_session, source.id)) == 1


def test_sync_http_error_keeps_old_nodes(db_session) -> None:
    """HTTP 500 同步失败时应保留上次成功节点。"""

    source = _create_source(db_session, "airport_fail")
    success_client = _mock_client(
        lambda request: httpx.Response(200, text=_valid_subscription("fail"))
    )
    SyncService(db_session, http_client=success_client).sync_source(source)

    fail_client = _mock_client(lambda request: httpx.Response(500, text="server error"))
    result = SyncService(db_session, http_client=fail_client).sync_source(source)

    assert result.status == "failed"
    assert result.error == "上游返回 HTTP 500"
    db_session.refresh(source)
    assert source.node_count == 2
    assert source.version == 1
    assert source.last_sync_status == "failed"
    assert NodeRepository(db_session).count_by_source(source.id) == 2
    assert len(_sync_logs(db_session, source.id)) == 2


def test_sync_empty_content_keeps_old_nodes_by_default(db_session) -> None:
    """空内容默认视为异常，旧节点不清空。"""

    source = _create_source(db_session, "airport_empty")
    success_client = _mock_client(
        lambda request: httpx.Response(200, text=_valid_subscription("empty"))
    )
    SyncService(db_session, http_client=success_client).sync_source(source)

    empty_client = _mock_client(lambda request: httpx.Response(200, text=""))
    result = SyncService(db_session, http_client=empty_client).sync_source(source)

    assert result.status == "failed"
    assert "空内容" in result.error
    db_session.refresh(source)
    assert source.node_count == 2
    assert NodeRepository(db_session).count_by_source(source.id) == 2


def test_sync_empty_content_override_clears_nodes(db_session) -> None:
    """开启 allow_empty_override 后，空订阅才允许覆盖旧节点。"""

    source = _create_source(db_session, "airport_override")
    success_client = _mock_client(
        lambda request: httpx.Response(200, text=_valid_subscription("override"))
    )
    SyncService(db_session, http_client=success_client).sync_source(source)

    source.allow_empty_override = True
    db_session.commit()
    empty_client = _mock_client(lambda request: httpx.Response(200, text=""))
    result = SyncService(db_session, http_client=empty_client).sync_source(source)

    assert result.status == "success"
    assert result.node_count == 0
    db_session.refresh(source)
    assert source.node_count == 0
    assert source.version == 2
    assert NodeRepository(db_session).count_by_source(source.id) == 0


def test_sync_invalid_content_keeps_old_nodes(db_session) -> None:
    """HTML/无效内容同步失败时保留旧节点。"""

    source = _create_source(db_session, "airport_html")
    success_client = _mock_client(
        lambda request: httpx.Response(200, text=_valid_subscription("html"))
    )
    SyncService(db_session, http_client=success_client).sync_source(source)

    html_client = _mock_client(
        lambda request: httpx.Response(200, text="<html><body>login</body></html>")
    )
    result = SyncService(db_session, http_client=html_client).sync_source(source)

    assert result.status == "failed"
    assert "HTML" in result.error
    db_session.refresh(source)
    assert source.node_count == 2
    assert NodeRepository(db_session).count_by_source(source.id) == 2
