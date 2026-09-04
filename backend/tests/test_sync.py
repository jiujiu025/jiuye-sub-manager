"""上游同步业务测试：成功、失败保留旧节点、空订阅策略、异常分类。"""

from __future__ import annotations

import base64

import pytest
from curl_cffi.requests import errors as curl_errors
from sqlalchemy import select

from app.core.config import get_settings
from app.db import SessionLocal
from app.models.log import SyncLog
from app.models.source import Source
from app.repositories.node_repo import NodeRepository
from app.services.sync_service import SyncService
from tests.fakes import FakeClient, FakeResponse


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


def _client_with(text: str, status: int = 200) -> FakeClient:
    return FakeClient(
        lambda url, kwargs: FakeResponse(status_code=status, text=text)
    )


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
    client = _client_with(_valid_subscription())
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


def test_sync_replacement_preserves_manually_disabled_state(db_session) -> None:
    """同步重建同一指纹节点时应保留管理员手动禁用状态。"""

    source = _create_source(db_session, "airport_disabled")
    content = _valid_subscription("disabled")
    service = SyncService(db_session, http_client=_client_with(content))
    assert service.sync_source(source).status == "success"

    node = NodeRepository(db_session).list_by_source(source.id)[0]
    node.enabled = False
    # 模拟 006 migration 前创建的旧节点，数据库中还没有稳定标识。
    node.source_node_key = None
    db_session.commit()

    result = SyncService(db_session, http_client=_client_with(content)).sync_source(source)
    assert result.status == "success"
    nodes = NodeRepository(db_session).list_by_source(source.id)
    disabled = next(item for item in nodes if item.node_fingerprint == node.node_fingerprint)
    assert disabled.enabled is False


def test_sync_endpoint_change_preserves_disabled_state_by_stable_uuid(db_session) -> None:
    """上游只变更 IP/端口时，UUID 相同的 disabled 节点仍应保持禁用。"""

    source = _create_source(db_session, "airport_endpoint_change")
    first = (
        "vless://00000000-0000-0000-0000-000000000010@old.example.com:443"
        "?security=tls#stable-node"
    )
    second = (
        "vless://00000000-0000-0000-0000-000000000010@new.example.com:8443"
        "?security=tls#stable-node"
    )
    assert SyncService(db_session, http_client=_client_with(first)).sync_source(source).status == "success"
    node = NodeRepository(db_session).list_by_source(source.id)[0]
    node.enabled = False
    db_session.commit()

    result = SyncService(db_session, http_client=_client_with(second)).sync_source(source)

    assert result.status == "success"
    nodes = NodeRepository(db_session).list_by_source(source.id)
    assert len(nodes) == 1
    assert nodes[0].server == "new.example.com"
    assert nodes[0].port == 8443
    assert nodes[0].enabled is False
    assert nodes[0].source_node_key


@pytest.mark.parametrize("status", [403, 404, 500])
def test_sync_http_status_keeps_old_nodes(db_session, status: int) -> None:
    """HTTP 403/404/500 同步失败时应保留上次成功节点。"""

    source = _create_source(db_session, f"airport_http_{status}")
    success_client = _client_with(_valid_subscription(f"http{status}"))
    SyncService(db_session, http_client=success_client).sync_source(source)

    fail_client = _client_with("error", status=status)
    result = SyncService(db_session, http_client=fail_client).sync_source(source)

    assert result.status == "failed"
    assert result.error == f"上游返回 HTTP {status}"
    db_session.refresh(source)
    assert source.node_count == 2
    assert source.version == 1
    assert source.last_sync_status == "failed"
    assert NodeRepository(db_session).count_by_source(source.id) == 2
    assert len(_sync_logs(db_session, source.id)) == 2


def test_sync_timeout_classification(db_session) -> None:
    """curl_cffi 超时异常应归类为上游请求超时。"""

    source = _create_source(db_session, "airport_timeout")
    client = FakeClient(
        lambda url, kwargs: (_ for _ in ()).throw(
            curl_errors.RequestsError("Operation timed out")
        )
    )
    result = SyncService(db_session, http_client=client).sync_source(source)

    assert result.status == "failed"
    assert result.error == "上游请求超时"
    db_session.refresh(source)
    assert source.node_count == 0


def test_sync_tls_error_classification(db_session) -> None:
    """TLS 握手中断应归类为明确文案。"""

    source = _create_source(db_session, "airport_tls")
    client = FakeClient(
        lambda url, kwargs: (_ for _ in ()).throw(
            curl_errors.RequestsError("SSL: UNEXPECTED_EOF_WHILE_READING")
        )
    )
    result = SyncService(db_session, http_client=client).sync_source(source)

    assert result.status == "failed"
    assert result.error == "TLS 握手失败（上游中断连接）"


def test_sync_client_uses_timeout_verify_and_user_agent(db_session) -> None:
    """同步请求应携带配置的超时、证书验证与浏览器 User-Agent。"""

    source = _create_source(db_session, "airport_params")
    client = _client_with(_valid_subscription("params"))
    SyncService(db_session, http_client=client).sync_source(source)

    call = client.calls[0]
    settings = get_settings()
    assert call["timeout"] == settings.http_timeout_seconds
    assert call["verify"] is True
    assert call["allow_redirects"] is True
    assert call["headers"]["User-Agent"] == settings.upstream_user_agent


def test_sync_empty_content_keeps_old_nodes_by_default(db_session) -> None:
    """空内容默认视为异常，旧节点不清空。"""

    source = _create_source(db_session, "airport_empty")
    success_client = _client_with(_valid_subscription("empty"))
    SyncService(db_session, http_client=success_client).sync_source(source)

    empty_client = _client_with("")
    result = SyncService(db_session, http_client=empty_client).sync_source(source)

    assert result.status == "failed"
    assert "空内容" in result.error
    db_session.refresh(source)
    assert source.node_count == 2
    assert NodeRepository(db_session).count_by_source(source.id) == 2


def test_sync_empty_content_override_clears_nodes(db_session) -> None:
    """开启 allow_empty_override 后，空订阅才允许覆盖旧节点。"""

    source = _create_source(db_session, "airport_override")
    success_client = _client_with(_valid_subscription("override"))
    SyncService(db_session, http_client=success_client).sync_source(source)

    source.allow_empty_override = True
    db_session.commit()
    empty_client = _client_with("")
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
    success_client = _client_with(_valid_subscription("html"))
    SyncService(db_session, http_client=success_client).sync_source(source)

    html_client = _client_with("<html><body>login</body></html>")
    result = SyncService(db_session, http_client=html_client).sync_source(source)

    assert result.status == "failed"
    assert "HTML" in result.error
    db_session.refresh(source)
    assert source.node_count == 2
    assert NodeRepository(db_session).count_by_source(source.id) == 2


def test_sync_commit_failure_rolls_back_replacement_and_cross_source_delete(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """写入失败时旧节点和跨来源去重删除都必须回滚。"""

    # 先创建待同步的新来源，使其在默认创建顺序中拥有更高优先级。
    new_source = _create_source(db_session, "airport_new")
    old_source = _create_source(db_session, "airport_old")
    sync = SyncService(db_session, http_client=_client_with(_valid_subscription("old")))
    assert sync.sync_source(old_source).status == "success"
    old_nodes = NodeRepository(db_session).list_by_source(old_source.id)
    old_fingerprints = {node.node_fingerprint for node in old_nodes}

    replacement_content = (
        f"vless://uuid-old@hk-old.example.com:443?security=reality#old\n"
        "vless://uuid-new@new.example.com:443#new"
    )
    sync = SyncService(db_session, http_client=_client_with(replacement_content))

    def fail_bulk_add(nodes):
        raise RuntimeError("模拟写入失败")

    monkeypatch.setattr(sync.node_repo, "bulk_add", fail_bulk_add)
    result = sync.sync_source(new_source)

    assert result.status == "failed"
    assert {
        node.node_fingerprint
        for node in NodeRepository(db_session).list_by_source(old_source.id)
    } == old_fingerprints
    assert NodeRepository(db_session).count_by_source(new_source.id) == 0
    db_session.refresh(old_source)
    db_session.refresh(new_source)
    assert old_source.node_count == 2
    assert new_source.node_count == 0
    assert new_source.version == 0
