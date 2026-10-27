"""节点健康检测和告警去重测试。"""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from sqlalchemy import select

from app.db import SessionLocal
from app.models.notification import Notification
from app.models.node import Node
from app.services import node_health_service
from app.services.node_health_service import (
    NodeHealthService,
    NodeProbeTarget,
    ProbeResult,
)
from app.exporters.singbox import SingboxExporter


@pytest.fixture
def auth_headers(client) -> dict[str, str]:
    """为健康检测接口获取管理员令牌。"""

    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_node(client, auth_headers: dict[str, str], suffix: str = "201") -> int:
    response = client.post(
        "/api/nodes",
        json={
            "name": f"健康检测测试节点-{suffix}",
            "type": "vless",
            "server": "health-test.example.com",
            "port": 443,
            "uuid": f"00000000-0000-0000-0000-000000000{suffix}",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_manual_health_check_updates_node(
    client, auth_headers: dict[str, str], monkeypatch
) -> None:
    """手动检测应返回并持久化最近一次探测结果。"""

    node_id = _create_node(client, auth_headers, "201")
    monkeypatch.setattr(
        node_health_service,
        "probe_node",
        lambda target, timeout: ProbeResult("healthy", "节点服务器可连接", 23),
    )

    response = client.post(f"/api/nodes/{node_id}/health/check", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["latency_ms"] == 23
    db = SessionLocal()
    try:
        node = db.get(Node, node_id)
        assert node is not None
        assert node.health_status == "healthy"
        assert node.health_latency_ms == 23
    finally:
        db.close()


def test_manual_all_health_endpoint_uses_full_scope(
    client, auth_headers: dict[str, str], monkeypatch
) -> None:
    """资源池的全部检测接口必须调用全量模式并返回检测数量。"""

    called = {}

    def fake_run_all(self, *, include_all: bool = False) -> int:
        called["include_all"] = include_all
        return 7

    monkeypatch.setattr(NodeHealthService, "run_all", fake_run_all)
    response = client.post("/api/nodes/health/check-all", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"checked": 7}
    assert called["include_all"] is True


def test_health_alerts_after_threshold_and_recovers_without_duplicates(
    client, auth_headers: dict[str, str], monkeypatch
) -> None:
    """连续失败才告警，恢复也只告警一次。"""

    node_id = _create_node(client, auth_headers, "202")
    result = ProbeResult("offline", "目标端口拒绝连接", None)
    monkeypatch.setattr(node_health_service, "probe_node", lambda target, timeout: result)
    db = SessionLocal()
    try:
        node = db.get(Node, node_id)
        assert node is not None
        service = NodeHealthService(db)
        service.run_node(node)
        service.run_node(node)
        service.run_node(node)
        db.expire_all()
        stored = db.get(Node, node_id)
        assert stored is not None
        assert stored.health_status == "offline"
        assert stored.health_failure_count == 3
        alerts = db.scalars(
            select(Notification).where(
                Notification.kind == "node_health",
                Notification.target_id == node_id,
            )
        ).all()
        assert len(alerts) == 1

        recovered = ProbeResult("healthy", "节点服务器可连接", 18)
        monkeypatch.setattr(node_health_service, "probe_node", lambda target, timeout: recovered)
        service.run_node(stored)
        service.run_node(stored)
        alerts = db.scalars(
            select(Notification).where(
                Notification.kind == "node_health",
                Notification.target_id == node_id,
            )
        ).all()
        assert len(alerts) == 2
        assert {item.title for item in alerts} == {"线路离线", "线路已恢复"}
    finally:
        db.close()


@pytest.mark.parametrize(
    "node_type, fields",
    [
        ("vless", {"uuid": "uuid", "security": "reality", "public_key": "key", "short_id": "sid"}),
        ("vmess", {"uuid": "uuid", "cipher": "auto"}),
        ("shadowsocks", {"cipher": "aes-256-gcm", "password": "password"}),
        ("trojan", {"password": "password", "tls": True}),
        ("socks", {}),
        ("http", {}),
        ("hysteria", {"password": "password", "tls": True}),
        ("hysteria2", {"password": "password", "tls": True}),
        ("tuic", {"uuid": "uuid", "password": "password", "tls": True}),
        ("anytls", {"password": "password", "tls": True}),
    ],
)
def test_singbox_health_outbound_supports_all_node_types(node_type, fields) -> None:
    """完整检测生成的 sing-box 出站配置应覆盖节点池支持的协议。"""

    node = SimpleNamespace(
        type=node_type,
        server="node.example.com",
        port=443,
        uuid=None,
        password=None,
        username=None,
        cipher=None,
        network="tcp",
        security=None,
        tls=None,
        sni="node.example.com",
        fingerprint=None,
        public_key=None,
        short_id=None,
        path=None,
        host=None,
        metadata_json={},
    )
    for key, value in fields.items():
        setattr(node, key, value)

    outbound = SingboxExporter._to_outbound(node, "health-node")

    assert outbound["tag"] == "health-node"
    assert outbound["server"] == "node.example.com"
    assert outbound["server_port"] == 443


@pytest.mark.parametrize("node_type", ["hysteria", "hysteria2"])
def test_hysteria_speed_aliases_are_numeric(node_type) -> None:
    """Hysteria 链接中的速度参数应转换为 sing-box 所需的整数。"""

    node = SimpleNamespace(
        type=node_type,
        server="node.example.com",
        port=443,
        uuid="00000000-0000-0000-0000-000000000001" if node_type == "hysteria2" else None,
        password="password",
        username=None,
        cipher=None,
        network="udp",
        security=None,
        tls=True,
        sni="node.example.com",
        fingerprint="chrome",
        public_key=None,
        short_id=None,
        path=None,
        host=None,
        metadata_json={"upmbps": "10", "downmbps": "50"},
    )

    outbound = SingboxExporter._to_outbound(node, "health-node")

    assert outbound["up_mbps"] == 10
    assert outbound["down_mbps"] == 50


def test_missing_singbox_is_unknown(monkeypatch) -> None:
    """检测依赖缺失时不应把线路标记为异常。"""

    monkeypatch.setattr(node_health_service.shutil, "which", lambda _: None)
    monkeypatch.setattr(node_health_service.os.path, "isfile", lambda _: False)
    target = NodeProbeTarget(
        node_id=1,
        name="依赖测试节点",
        node_type="vless",
        server="node.example.com",
        port=443,
        outbound={"type": "vless"},
    )

    result = node_health_service.probe_node(target, 5)

    assert result.status == "unknown"


def test_basic_udp_probe_is_explicitly_limited() -> None:
    """基础模式不能伪造 UDP 远端可用，必须明确提示切换完整模式。"""

    target = NodeProbeTarget(
        node_id=1,
        name="UDP 基础检测节点",
        node_type="hysteria2",
        server="udp.example.com",
        port=443,
        outbound={"type": "hysteria2"},
    )

    result = node_health_service.probe_basic_node(target, 1)

    assert result.status == "unknown"
    assert result.tcp_status == "not_applicable"
    assert result.tls_status == "not_applicable"
    assert result.udp_status == "unknown"
    assert "UDP" in result.detail
    assert "完整模式" in result.detail


def test_full_udp_probe_records_udp_success(monkeypatch) -> None:
    """完整模式访问测试网址成功时，UDP 协议应记录真实的通过结果。"""

    class FakeProcess:
        stderr = None

        def poll(self):
            return None

    class FakeResponse:
        status_code = 204

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(node_health_service, "get_settings", lambda: SimpleNamespace(
        sing_box_path="sing-box",
        health_test_url="https://health.example.com/",
    ))
    monkeypatch.setattr(node_health_service.shutil, "which", lambda _: "sing-box")
    monkeypatch.setattr(node_health_service.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0,
        stderr="",
    ))
    monkeypatch.setattr(node_health_service.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(node_health_service, "_wait_for_proxy", lambda *args: (True, ""))
    monkeypatch.setattr(node_health_service, "_terminate_process", lambda process: None)
    monkeypatch.setattr(node_health_service, "_free_local_port", lambda: 19000)
    monkeypatch.setattr(node_health_service.httpx, "Client", FakeClient)

    result = node_health_service.probe_node(
        NodeProbeTarget(
            node_id=1,
            name="UDP 完整检测节点",
            node_type="hysteria2",
            server="udp.example.com",
            port=443,
            outbound={"type": "hysteria2", "tls": {"enabled": True}},
        ),
        5,
    )

    assert result.status == "healthy"
    assert result.tcp_status == "not_applicable"
    assert result.udp_status == "passed"
    assert result.udp_latency_ms is not None


def test_health_diagnostics_explain_network_and_latency_causes() -> None:
    """健康检测原因应区分线路故障、协议故障和延迟异常。"""

    assert "线路不通" in node_health_service._error_detail(ConnectionRefusedError())
    assert "TLS/Reality 握手异常" in node_health_service._classify_process_error(
        "reality handshake failed"
    )
    assert "延迟异常" in node_health_service._latency_detail(3000)


def test_run_all_only_checks_custom_nodes(
    client, auth_headers: dict[str, str], monkeypatch
) -> None:
    """定时检测只处理用户导入或创建的自有线路。"""

    custom_id = _create_node(client, auth_headers, "203")
    upstream_id = _create_node(client, auth_headers, "204")
    db = SessionLocal()
    try:
        upstream = db.get(Node, upstream_id)
        assert upstream is not None
        upstream.source_type = "upstream"
        for existing in db.scalars(select(Node)).all():
            if existing.id not in {custom_id, upstream_id}:
                existing.enabled = False
        db.commit()
        monkeypatch.setattr(
            node_health_service,
            "probe_node",
            lambda target, timeout: ProbeResult("healthy", "节点服务器可连接", 12),
        )

        assert NodeHealthService(db).run_all() == 1
        custom = db.get(Node, custom_id)
        upstream = db.get(Node, upstream_id)
        assert custom is not None and custom.health_status == "healthy"
        assert upstream is not None and upstream.health_status == "unknown"
    finally:
        db.close()


def test_run_all_checks_legacy_external_nodes_without_source_type(
    client, auth_headers: dict[str, str], monkeypatch
) -> None:
    """历史外部节点没有 source_type 时，定时健康检测仍应覆盖它。"""

    node_id = _create_node(client, auth_headers, "209")
    db = SessionLocal()
    try:
        node = db.get(Node, node_id)
        assert node is not None
        node.source_type = None
        node.node_category = "external"
        for existing in db.scalars(select(Node)).all():
            if existing.id != node_id:
                existing.enabled = False
        db.commit()
        monkeypatch.setattr(
            node_health_service,
            "probe_node",
            lambda target, timeout: ProbeResult("healthy", "节点服务器可连接", 12),
        )

        assert NodeHealthService(db).run_all() == 1
        checked = db.get(Node, node_id)
        assert checked is not None
        assert checked.health_status == "healthy"
    finally:
        db.close()


def test_run_all_can_include_all_enabled_nodes(
    client, auth_headers: dict[str, str], monkeypatch
) -> None:
    """手动全量检测可以覆盖上游节点，同时保留定时检测的默认范围。"""

    custom_id = _create_node(client, auth_headers, "207")
    upstream_id = _create_node(client, auth_headers, "208")
    db = SessionLocal()
    try:
        upstream = db.get(Node, upstream_id)
        assert upstream is not None
        upstream.source_type = "upstream"
        for existing in db.scalars(select(Node)).all():
            if existing.id not in {custom_id, upstream_id}:
                existing.enabled = False
        db.commit()
        monkeypatch.setattr(
            node_health_service,
            "probe_node",
            lambda target, timeout: ProbeResult("healthy", "节点服务器可连接", 12),
        )

        assert NodeHealthService(db).run_all(include_all=True) == 2
        custom = db.get(Node, custom_id)
        upstream = db.get(Node, upstream_id)
        assert custom is not None and custom.health_status == "healthy"
        assert upstream is not None and upstream.health_status == "healthy"
    finally:
        db.close()


def test_invalid_custom_node_does_not_abort_batch(
    client, auth_headers: dict[str, str], monkeypatch
) -> None:
    """单个协议类型异常的节点不应阻断其他节点检测。"""

    good_id = _create_node(client, auth_headers, "205")
    bad_id = _create_node(client, auth_headers, "206")
    db = SessionLocal()
    try:
        bad = db.get(Node, bad_id)
        assert bad is not None
        bad.type = "unsupported"
        for existing in db.scalars(select(Node)).all():
            if existing.id not in {good_id, bad_id}:
                existing.enabled = False
        db.commit()
        monkeypatch.setattr(
            node_health_service,
            "probe_node",
            lambda target, timeout: ProbeResult("healthy", "节点服务器可连接", 12),
        )

        assert NodeHealthService(db).run_all() == 2
        good = db.get(Node, good_id)
        bad = db.get(Node, bad_id)
        assert good is not None and good.health_status == "healthy"
        assert bad is not None and "节点配置无效" in (bad.health_detail or "")
    finally:
        db.close()
