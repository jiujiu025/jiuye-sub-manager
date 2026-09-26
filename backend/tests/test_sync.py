"""上游同步业务测试：成功、失败保留旧节点、空订阅策略、异常分类。"""

from __future__ import annotations

import base64

import pytest
from curl_cffi import CurlOpt
from curl_cffi.requests import errors as curl_errors
from sqlalchemy import select

from app.core.config import get_settings
from app.core.cache import cache_service
from app.db import SessionLocal
from app.models.log import SyncLog
from app.models.source import Source
from app.repositories.node_repo import NodeRepository
from app.services.sync_service import SyncService
from app.services.subscription_service import SubscriptionService
from app.models.package import Package, PackageRule
from app.models.user import User
from app.schemas.source import SourceUpdate
from app.services.source_service import SourceService
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
    assert call["allow_redirects"] is False
    assert call["headers"]["User-Agent"] == settings.upstream_user_agent


def test_sync_uses_conditional_headers_and_preserves_nodes_on_304(db_session) -> None:
    """上游未变化时使用 ETag/Last-Modified，304 不重建节点。"""

    source = _create_source(db_session, "airport_conditional")
    first_client = FakeClient(
        lambda url, kwargs: FakeResponse(
            text=_valid_subscription("conditional"),
            headers={"etag": '"v1"', "last-modified": "Wed, 01 Jan 2025 00:00:00 GMT"},
        )
    )
    assert SyncService(db_session, http_client=first_client).sync_source(source).status == "success"
    old_version = source.version
    old_node_ids = {node.id for node in NodeRepository(db_session).list_by_source(source.id)}

    second_client = FakeClient(
        lambda url, kwargs: FakeResponse(status_code=304, headers={})
    )
    result = SyncService(db_session, http_client=second_client).sync_source(source)

    assert result.status == "success"
    assert result.node_count == 2
    assert source.version == old_version
    assert {node.id for node in NodeRepository(db_session).list_by_source(source.id)} == old_node_ids
    assert second_client.calls[0]["headers"]["If-None-Match"] == '"v1"'
    assert second_client.calls[0]["headers"]["If-Modified-Since"] == "Wed, 01 Jan 2025 00:00:00 GMT"
    assert source.consecutive_failures == 0


def test_source_target_change_clears_conditional_cache(db_session) -> None:
    """来源地址或格式变化后不得把旧 ETag 发送给新内容。"""

    source = _create_source(db_session, "airport_change_target")
    source.etag = '"old"'
    source.last_modified = "Wed, 01 Jan 2025 00:00:00 GMT"
    db_session.commit()
    admin = db_session.scalar(select(User).where(User.username == "admin"))

    assert admin is not None
    SourceService(db_session).update(
        source,
        SourceUpdate(url="https://new-provider.example.com/sub"),
        admin,
    )
    assert source.etag is None
    assert source.last_modified is None


def test_default_curl_request_pins_checked_dns_result(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """默认 curl 请求必须把已校验的公网解析结果固定到本次连接。"""

    monkeypatch.setattr(
        "app.services.sync_service.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )

    class FakePinnedCurl:
        options: dict[object, object] = {}
        writer = None
        headers = None

        def setopt(self, option, value):
            self.options[option] = value
            if option == CurlOpt.WRITEFUNCTION:
                self.writer = value
            elif option == CurlOpt.HEADERDATA:
                self.headers = value

        def perform(self):
            self.headers.write(b"HTTP/1.1 200 OK\r\ncontent-length: 4\r\n\r\n")
            self.writer(b"feed")

        def getinfo(self, _info):
            return 200

        def close(self):
            pass

    monkeypatch.setattr("app.services.sync_service.Curl", FakePinnedCurl)
    service = SyncService(db_session)

    assert service._fetch("https://provider.example.com/sub") == "feed"
    assert FakePinnedCurl.options[CurlOpt.RESOLVE] == [
        "provider.example.com:443:93.184.216.34"
    ]


def test_sync_rejects_mixed_public_and_private_dns_answers(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """域名任一解析结果为内网地址时必须整体拒绝，避免解析漂移绕过。"""

    source = _create_source(db_session, "airport_mixed_dns")
    monkeypatch.setattr(
        "app.services.sync_service.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (None, None, None, None, ("93.184.216.34", 443)),
            (None, None, None, None, ("169.254.169.254", 443)),
        ],
    )
    result = SyncService(
        db_session, http_client=_client_with(_valid_subscription("mixed-dns"))
    ).sync_source(source)

    assert result.status == "failed"
    assert "内网" in (result.error or "")


def test_sync_rejects_private_redirect_target(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """重定向到内网地址时必须在请求前阻断。"""

    source = _create_source(db_session, "airport_private_redirect")
    monkeypatch.setattr(
        "app.services.sync_service.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    client = FakeClient(
        lambda url, kwargs: FakeResponse(
            status_code=302,
            headers={"location": "http://127.0.0.1/private"},
        )
    )

    result = SyncService(db_session, http_client=client).sync_source(source)

    assert result.status == "failed"
    assert "内网" in (result.error or "")
    assert len(client.calls) == 1


def test_sync_rejects_dns_resolved_private_target(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """域名解析到内网地址时也必须阻断。"""

    source = _create_source(db_session, "airport_private_dns")
    monkeypatch.setattr(
        "app.services.sync_service.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("10.0.0.8", 443))],
    )
    client = _client_with(_valid_subscription("private-dns"))

    result = SyncService(db_session, http_client=client).sync_source(source)

    assert result.status == "failed"
    assert "内网" in (result.error or "")
    assert client.calls == []


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


def test_failed_sync_keeps_existing_subscription_cache(db_session) -> None:
    """同步失败时不得递增节点版本或清空上一次成功的订阅缓存。"""

    cache_service.invalidate_all()
    source = _create_source(db_session, "airport_cached_failure")
    success_client = _client_with(_valid_subscription("cached-failure"))
    assert SyncService(db_session, http_client=success_client).sync_source(source).status == "success"

    package = Package(id=987654, token_hash="a" * 64, name="缓存测试套餐")
    cache_value = ("cached-subscription", 2)
    SubscriptionService.set_cached(package, cache_value[0], "clash", cache_value[1])
    assert SubscriptionService.get_cached_entry(package) == cache_value

    result = SyncService(
        db_session, http_client=_client_with("error", status=404)
    ).sync_source(source)

    assert result.status == "failed"
    assert SubscriptionService.get_cached_entry(package) == cache_value


def test_successful_sync_invalidates_related_cache_only(db_session) -> None:
    """同步成功时只失效受影响来源的套餐缓存。"""

    cache_service.invalidate_all()
    source = _create_source(db_session, "airport_precise_cache")
    other_source_name = "airport_unrelated_cache"
    assert SyncService(
        db_session, http_client=_client_with(_valid_subscription("precise-cache"))
    ).sync_source(source).status == "success"

    related = Package(
        name="相关缓存套餐",
        token_hash="c" * 64,
        token_prefix="related",
    )
    unrelated = Package(
        name="无关缓存套餐",
        token_hash="d" * 64,
        token_prefix="unrelated",
    )
    db_session.add_all([related, unrelated])
    db_session.flush()
    db_session.add_all(
        [
            PackageRule(package_id=related.id, source_filter=[source.name]),
            PackageRule(package_id=unrelated.id, source_filter=[other_source_name]),
        ]
    )
    db_session.commit()
    related_cache = ("related-cache", 2)
    unrelated_cache = ("unrelated-cache", 3)
    SubscriptionService.set_cached(related, related_cache[0], "clash", related_cache[1])
    SubscriptionService.set_cached(
        unrelated, unrelated_cache[0], "clash", unrelated_cache[1]
    )

    assert SyncService(
        db_session, http_client=_client_with(_valid_subscription("precise-cache-new"))
    ).sync_source(source).status == "success"

    assert SubscriptionService.get_cached_entry(related) is None
    assert SubscriptionService.get_cached_entry(unrelated) == unrelated_cache


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


def test_sync_invalid_protocol_node_keeps_previous_successful_nodes(db_session) -> None:
    """解析出缺少关键字段的节点时，同步失败且保留旧节点。"""

    source = _create_source(db_session, "airport_invalid_protocol")
    valid = _valid_subscription("before-invalid")
    assert SyncService(
        db_session, http_client=_client_with(valid)
    ).sync_source(source).status == "success"

    malformed = (
        "proxies:\n"
        "  - name: invalid-vless\n"
        "    type: vless\n"
        "    server: invalid.example.com\n"
        "    port: 443\n"
    )
    result = SyncService(
        db_session, http_client=_client_with(malformed)
    ).sync_source(source)

    assert result.status == "failed"
    assert "UUID" in (result.error or "")
    assert NodeRepository(db_session).count_by_source(source.id) == 2
    assert all(
        node.server != "invalid.example.com"
        for node in NodeRepository(db_session).list_by_source(source.id)
    )
