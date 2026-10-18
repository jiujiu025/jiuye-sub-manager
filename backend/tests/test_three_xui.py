"""3x-ui 服务器和异步转发功能测试。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.integrations.three_xui.adapter import (
    ForwardProvision,
    ThreeXUIAdapter,
    ThreeXUIError,
    _build_client_email,
    _extract_xray_config,
    normalize_api_url,
)
from app.models.node import Node
from app.models.three_xui import ForwardTask, ForwardedNodeMapping, ThreeXUIServer
from app.services.three_xui_service import ThreeXUIService
from app.utils.fingerprint import build_node_fingerprint


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _server_payload() -> dict[str, object]:
    suffix = uuid4().hex[:8]
    return {
        "name": f"测试面板-{suffix}",
        "ip": "198.51.100.20",
        "api_url": "https://panel.example.test",
        "api_token": "test-three-xui-token",
        "version": "3.8.5",
    }


def test_three_xui_client_email_is_unique_and_not_node_remark() -> None:
    first = _build_client_email("submgr-in-38")
    second = _build_client_email("submgr-in-38")

    assert first != second
    assert first.startswith("submgr-submgr-in-38-")
    assert all(char.isalnum() or char in ".-_" for char in first)


def test_three_xui_xray_config_accepts_common_response_shapes() -> None:
    config = {"outbounds": [], "routing": {"rules": []}}

    assert _extract_xray_config({"obj": {"xraySetting": config}}) == config
    assert _extract_xray_config({"obj": {"xraySetting": '{"outbounds": [], "routing": {"rules": []}}'}}) == config
    assert _extract_xray_config(config) == config
    assert _extract_xray_config({"obj": {"message": "ok"}}) is None


def test_three_xui_normalizes_docs_url_without_dropping_web_base_path() -> None:
    assert normalize_api_url(
        "https://panel.example.test/custom-base/panel/api-docs"
    ) == "https://panel.example.test/custom-base"
    assert normalize_api_url(
        "https://panel.example.test/custom-base/"
    ) == "https://panel.example.test/custom-base"


def test_three_xui_url_keeps_web_base_path() -> None:
    adapter = object.__new__(ThreeXUIAdapter)
    adapter.base_url = "https://panel.example.test/custom-base"
    assert adapter._url("/panel/api/inbounds/add") == (
        "https://panel.example.test/custom-base/panel/api/inbounds/add"
    )


def test_three_xui_404_includes_method_path_and_panel_message(monkeypatch) -> None:
    adapter = object.__new__(ThreeXUIAdapter)
    adapter.token = "not-a-real-token"
    adapter.base_url = "https://panel.example.test/custom-base"
    adapter.timeout = 1
    events = []
    adapter.request_logger = events.append

    class FakeResponse:
        status_code = 404

        def json(self):
            return {"success": False, "msg": "Not Found"}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, **kwargs):
            assert url.endswith("/custom-base/panel/api/inbounds/add")
            assert kwargs["headers"]["Authorization"] == "Bearer not-a-real-token"
            return FakeResponse()

    monkeypatch.setattr("app.integrations.three_xui.adapter.httpx.Client", FakeClient)
    with pytest.raises(ThreeXUIError) as exc_info:
        adapter._request("POST", "/panel/api/inbounds/add", json={"remark": "test"})

    message = str(exc_info.value)
    assert "POST /panel/api/inbounds/add" in message
    assert "HTTP 404" in message
    assert "Not Found" in message
    assert events[0]["success"] is False
    assert "not-a-real-token" not in str(events[0])


def test_three_xui_delete_inbound_treats_remote_404_as_idempotent(monkeypatch) -> None:
    adapter = object.__new__(ThreeXUIAdapter)

    def fake_request(*args, **kwargs):
        raise ThreeXUIError("3x-ui API 请求失败：HTTP 404", status_code=404)

    monkeypatch.setattr(adapter, "_request", fake_request)
    adapter.delete_inbound(12, ignore_missing=True)


def test_three_xui_prefers_links_for_requested_inbound(monkeypatch) -> None:
    adapter = object.__new__(ThreeXUIAdapter)
    paths = []

    def fake_request(method, path, **kwargs):
        paths.append(path)
        if path.endswith("/get/12"):
            return {
                "success": True,
                "obj": {
                    "id": 12,
                    "links": ["vless://requested.example.test:443"],
                },
            }
        raise AssertionError("不应在指定入站已有链接时读取全部链接")

    monkeypatch.setattr(adapter, "_request", fake_request)
    assert adapter.get_inbound_links(12) == ["vless://requested.example.test:443"]
    assert paths == ["/panel/api/inbounds/get/12"]


def test_three_xui_add_inbound_uses_documented_json_payload(monkeypatch) -> None:
    adapter = object.__new__(ThreeXUIAdapter)
    captured = {}

    def fake_request(method, path, **kwargs):
        captured.update(method=method, path=path, **kwargs)
        return {"success": True, "obj": {"id": 123}}

    monkeypatch.setattr(adapter, "_request", fake_request)
    result = adapter.add_inbound(
        {
            "remark": "测试入站",
            "tag": "submgr-in-test",
            "port": 24443,
            "settings": {"clients": []},
            "streamSettings": {"network": "tcp"},
        }
    )

    assert result["id"] == 123
    assert captured["method"] == "POST"
    assert captured["path"] == "/panel/api/inbounds/add"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["json"]["port"] == 24443
    assert captured["json"]["tag"] == "submgr-in-test"
    assert captured["json"]["settings"] == {"clients": []}
    assert captured["json"]["streamSettings"] == {"network": "tcp"}


def test_three_xui_retries_duplicate_client_email(monkeypatch) -> None:
    adapter = object.__new__(ThreeXUIAdapter)
    payload = {"settings": {"clients": [{"email": "old-email"}]}}
    attempts = []

    def fake_add(value):
        attempts.append(value["settings"]["clients"][0]["email"])
        if len(attempts) == 1:
            raise ThreeXUIError("Duplicate email: old-email")
        return {"id": 124}

    monkeypatch.setattr(adapter, "add_inbound", fake_add)
    result = adapter._add_inbound_with_unique_email(payload, "submgr-in-test")

    assert result["id"] == 124
    assert len(attempts) == 2
    assert attempts[0] == "old-email"
    assert attempts[1] != "old-email"


def test_three_xui_port_forward_creates_dokodemo_inbound(monkeypatch) -> None:
    """端口转发模式只创建直通入站，不读取分享链接或修改出站路由。"""

    adapter = object.__new__(ThreeXUIAdapter)
    captured: dict[str, object] = {}
    monkeypatch.setattr(adapter, "list_inbounds", lambda: [])

    def fake_add(payload):
        captured["payload"] = payload
        return {"id": 321, "tag": payload["tag"]}

    monkeypatch.setattr(adapter, "add_inbound", fake_add)
    monkeypatch.setattr(adapter, "restart_xray", lambda: captured.update(restarted=True))
    source = Node(type="vless", server="source.example.test", port=443, uuid="source-uuid")

    provision = adapter.provision_port_forward(
        source,
        listen_port=24443,
        remark="香港-198.51.100.20",
        target_address="198.51.100.20",
        inbound_tag="submgr-in-port",
    )

    assert provision.forward_mode == "port_forward"
    assert provision.inbound_id == 321
    assert captured["payload"]["protocol"] == "dokodemo-door"
    assert captured["payload"]["settings"] == {
        "address": "source.example.test",
        "port": 443,
        "network": "tcp",
    }
    assert captured["restarted"] is True


def test_three_xui_list_inbounds_falls_back_to_standard_endpoint(monkeypatch) -> None:
    adapter = object.__new__(ThreeXUIAdapter)
    paths = []

    def fake_request(method, path, **kwargs):
        paths.append(path)
        if path.endswith("/slim"):
            raise Exception("should not call slim after standard succeeds")
        return {"success": True, "obj": [{"id": 123, "port": 24443}]}

    monkeypatch.setattr(adapter, "_request", fake_request)
    assert adapter.list_inbounds() == [{"id": 123, "port": 24443}]
    assert paths == ["/panel/api/inbounds/list"]


def test_three_xui_server_token_is_encrypted_and_not_returned(
    client: TestClient,
) -> None:
    headers = _headers(client)
    response = client.post("/api/three-xui/servers", json=_server_payload(), headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert "api_token" not in body
    assert "api_token_encrypted" not in body
    assert body["api_token_prefix"] == "test-thr"

    db = SessionLocal()
    try:
        server = db.get(ThreeXUIServer, body["id"])
        assert server is not None
        assert server.api_token_encrypted != "test-three-xui-token"
    finally:
        db.close()


def test_three_xui_server_stores_normalized_panel_root_from_docs_url(
    client: TestClient,
) -> None:
    headers = _headers(client)
    payload = _server_payload()
    payload["api_url"] = "https://panel.example.test/custom-base/panel/api-docs"
    response = client.post("/api/three-xui/servers", json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json()["api_url"] == "https://panel.example.test/custom-base"


def test_three_xui_requires_admin(client: TestClient) -> None:
    response = client.get("/api/three-xui/servers")
    assert response.status_code == 401


def test_forward_task_accepts_only_external_nodes(client: TestClient) -> None:
    headers = _headers(client)
    server = client.post("/api/three-xui/servers", json=_server_payload(), headers=headers)
    assert server.status_code == 201

    db = SessionLocal()
    try:
        source = Node(
            source_name="上游测试来源",
            source_type="upstream",
            node_category="subscription",
            original_name="订阅节点",
            name="订阅节点",
            type="vless",
            server="upstream.example.test",
            port=443,
            uuid="00000000-0000-4000-0000-000000000100",
            node_fingerprint=build_node_fingerprint(
                node_type="vless",
                server="upstream.example.test",
                port=443,
                uuid="00000000-0000-4000-0000-000000000100",
            ),
        )
        db.add(source)
        db.commit()
        source_id = source.id
    finally:
        db.close()

    response = client.post(
        "/api/three-xui/forward",
        json={
            "source_node_id": source_id,
            "target_server_id": server.json()["id"],
            "template": "vless_tcp",
            "listen_port": 24443,
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "外部节点" in response.json()["detail"]


def test_forward_task_auto_allocates_ports_from_12900(
    client: TestClient,
) -> None:
    """未指定监听端口时，任务应从 12900 开始顺序预留端口。"""

    headers = _headers(client)
    server = client.post("/api/three-xui/servers", json=_server_payload(), headers=headers)
    assert server.status_code == 201
    server_id = server.json()["id"]
    nodes = []
    for index in range(2):
        response = client.post(
            "/api/nodes",
            json={
                "name": f"自动端口节点-{index}",
                "type": "vless",
                "server": f"auto-port-{index}.example.test",
                "port": 443,
                "uuid": f"00000000-0000-4000-0000-00000000015{index}",
            },
            headers=headers,
        )
        assert response.status_code == 201
        nodes.append(response.json()["id"])

    first = client.post(
        "/api/three-xui/forward",
        json={"source_node_id": nodes[0], "target_server_id": server_id},
        headers=headers,
    )
    second = client.post(
        "/api/three-xui/forward",
        json={"source_node_id": nodes[1], "target_server_id": server_id},
        headers=headers,
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["listen_port"] == 12900
    assert second.json()["listen_port"] == 12901

    db = SessionLocal()
    try:
        first_task = db.get(ForwardTask, first.json()["id"])
        assert first_task is not None and first_task.auto_port is True
    finally:
        db.close()


def test_create_test_inbound_endpoint_returns_remote_inbound_id(
    client: TestClient, monkeypatch
) -> None:
    """测试入站接口应调用适配器并返回远端入站 ID，不暴露 Token。"""

    headers = _headers(client)
    server = client.post("/api/three-xui/servers", json=_server_payload(), headers=headers)
    assert server.status_code == 201
    captured = {}

    def fake_create(self, **kwargs):
        captured.update(kwargs)
        return ForwardProvision(
            inbound_id=901,
            client_id="test-client-id",
            inbound_remark=kwargs["remark"],
            inbound_tag="submgr-test-tag",
            protocol="vless",
            server="198.51.100.20",
            port=kwargs["listen_port"],
            uuid="00000000-0000-4000-0000-000000000901",
            password=None,
            cipher=None,
            network="tcp",
            tls=False,
            sni=None,
            path=None,
            host=None,
            fingerprint=None,
            public_key=None,
            short_id=None,
            metadata={},
        )

    monkeypatch.setattr(ThreeXUIAdapter, "create_test_inbound", fake_create)
    response = client.post(
        f"/api/three-xui/servers/{server.json()['id']}/inbounds/test",
        json={"template": "vless_tcp"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["inbound_id"] == 901
    assert response.json()["port"] == 12900
    assert captured["listen_port"] == 12900
    assert "api_token" not in response.text


def test_forward_task_is_idempotent_and_saves_mapping(
    client: TestClient, monkeypatch
) -> None:
    headers = _headers(client)
    server_response = client.post("/api/three-xui/servers", json=_server_payload(), headers=headers)
    assert server_response.status_code == 201
    server_id = server_response.json()["id"]
    node_response = client.post(
        "/api/nodes",
        json={
            "name": "转发源节点",
            "type": "vless",
            "server": "source.example.test",
            "port": 443,
            "uuid": "00000000-0000-4000-0000-000000000101",
        },
        headers=headers,
    )
    assert node_response.status_code == 201
    node_id = node_response.json()["id"]

    first = client.post(
        "/api/three-xui/forward",
        json={"source_node_id": node_id, "target_server_id": server_id, "listen_port": 24444},
        headers=headers,
    )
    second = client.post(
        "/api/three-xui/forward",
        json={"source_node_id": node_id, "target_server_id": server_id, "listen_port": 24444},
        headers=headers,
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["progress"] == 0
    assert first.json()["stage"] == "等待后台处理"

    provision = ForwardProvision(
        inbound_id=301,
        client_id="00000000-0000-4000-0000-000000000201",
        inbound_remark="测试转发",
        inbound_tag="submgr-in-test",
        protocol="vless",
        server="198.51.100.20",
        port=24444,
        uuid="00000000-0000-4000-0000-000000000201",
        password=None,
        cipher=None,
        network="tcp",
        tls=False,
        sni=None,
        path=None,
        host=None,
        fingerprint=None,
        public_key=None,
        short_id=None,
        metadata={},
    )
    monkeypatch.setattr(ThreeXUIAdapter, "provision_forward", lambda *args, **kwargs: provision)
    monkeypatch.setattr(
        ThreeXUIAdapter,
        "get_inbound_links",
        lambda *args, **kwargs: [
            "vless://00000000-0000-4000-0000-000000000201@198.51.100.20:24444?encryption=none&type=tcp#测试转发"
        ],
    )
    monkeypatch.setattr(ThreeXUIAdapter, "cleanup_forward", lambda *args, **kwargs: None)

    db = SessionLocal()
    try:
        assert ThreeXUIService(db).process_pending() == 1
        task = db.get(ForwardTask, first.json()["id"])
        assert task is not None and task.status == "succeeded"
        assert task.progress == 100
        assert task.stage == "转发完成"
        mapping = db.scalar(select(ForwardedNodeMapping).where(ForwardedNodeMapping.forwarded_node_id == task.result_node_id))
        assert mapping is not None
        forwarded = db.get(Node, task.result_node_id)
        assert forwarded is not None and forwarded.node_category == "forwarded"
    finally:
        db.close()

    mappings = client.get("/api/three-xui/mappings", headers=headers)
    assert mappings.status_code == 200
    mapping_body = mappings.json()[0]
    assert "client_id" not in mapping_body
    assert mapping_body["client_id_masked"] == "0000...0201"
    assert "00000000-0000-4000-0000-000000000201" not in mappings.text

    forwarded_nodes = client.get("/api/nodes?source_kind=forwarded", headers=headers)
    assert forwarded_nodes.status_code == 200
    forwarded_body = forwarded_nodes.json()["items"][0]
    assert forwarded_body["forward_target_server_name"] == server_response.json()["name"]
    assert forwarded_body["forward_inbound_id"] == 301
    assert forwarded_body["forward_inbound_remark"] == "测试转发"
    assert forwarded_body["forward_inbound_endpoint"] == "198.51.100.20:24444"
    assert "00000000-0000-4000-0000-000000000201" not in forwarded_nodes.text


def test_nodes_referenced_by_three_xui_cannot_be_deleted(
    client: TestClient,
) -> None:
    headers = _headers(client)
    server = client.post("/api/three-xui/servers", json=_server_payload(), headers=headers)
    assert server.status_code == 201

    source = client.post(
        "/api/nodes",
        json={
            "name": "映射源节点",
            "type": "vless",
            "server": "source-delete.example.test",
            "port": 443,
            "uuid": "00000000-0000-4000-0000-000000000301",
        },
        headers=headers,
    )
    forwarded = client.post(
        "/api/nodes",
        json={
            "name": "映射目标节点",
            "type": "vless",
            "server": "forwarded-delete.example.test",
            "port": 8443,
            "uuid": "00000000-0000-4000-0000-000000000302",
        },
        headers=headers,
    )
    assert source.status_code == 201
    assert forwarded.status_code == 201

    db = SessionLocal()
    try:
        db.add(
            ForwardedNodeMapping(
                source_node_id=source.json()["id"],
                forwarded_node_id=forwarded.json()["id"],
                target_server_id=server.json()["id"],
                inbound_id=302,
                client_id="00000000-0000-4000-0000-000000000303",
                inbound_remark="删除保护测试",
                template="vless_tcp",
            )
        )
        db.commit()
    finally:
        db.close()

    source_delete = client.delete(
        f"/api/nodes/{source.json()['id']}", headers=headers
    )
    forwarded_delete = client.delete(
        f"/api/nodes/{forwarded.json()['id']}", headers=headers
    )
    assert source_delete.status_code == 409
    assert forwarded_delete.status_code == 409
    assert "转发映射" in source_delete.json()["detail"]


def test_deleting_forwarded_node_cleans_remote_mapping_first(
    client: TestClient, monkeypatch
) -> None:
    """删除已转发节点时，远端清理成功后才删除本地映射。"""

    headers = _headers(client)
    server = client.post("/api/three-xui/servers", json=_server_payload(), headers=headers)
    assert server.status_code == 201
    source = client.post(
        "/api/nodes",
        json={
            "name": "远端清理源节点",
            "type": "vless",
            "server": "cleanup-source.example.test",
            "port": 443,
            "uuid": "00000000-0000-4000-0000-000000000401",
        },
        headers=headers,
    )
    forwarded = client.post(
        "/api/nodes",
        json={
            "name": "远端清理目标节点",
            "type": "vless",
            "server": "cleanup-target.example.test",
            "port": 24401,
            "uuid": "00000000-0000-4000-0000-000000000402",
        },
        headers=headers,
    )
    assert source.status_code == 201
    assert forwarded.status_code == 201

    db = SessionLocal()
    try:
        forwarded_node = db.get(Node, forwarded.json()["id"])
        assert forwarded_node is not None
        forwarded_node.node_category = "forwarded"
        db.add(
            ForwardedNodeMapping(
                source_node_id=source.json()["id"],
                forwarded_node_id=forwarded_node.id,
                target_server_id=server.json()["id"],
                inbound_id=401,
                client_id="00000000-0000-4000-0000-000000000403",
                inbound_remark="清理测试",
                template="vless_tcp",
                metadata_json={
                    "inbound_tag": "submgr-in-cleanup",
                    "outbound_tag": "submgr-out-cleanup",
                },
            )
        )
        db.commit()
    finally:
        db.close()

    calls = []
    monkeypatch.setattr(
        ThreeXUIAdapter,
        "cleanup_forward",
        lambda self, inbound_id, inbound_tag, outbound_tag: calls.append(
            (inbound_id, inbound_tag, outbound_tag)
        ),
    )
    response = client.delete(f"/api/nodes/{forwarded.json()['id']}", headers=headers)
    assert response.status_code == 204
    assert calls == [(401, "submgr-in-cleanup", "submgr-out-cleanup")]

    db = SessionLocal()
    try:
        assert db.get(Node, forwarded.json()["id"]) is None
        assert db.scalar(
            select(ForwardedNodeMapping).where(
                ForwardedNodeMapping.forwarded_node_id == forwarded.json()["id"]
            )
        ) is None
    finally:
        db.close()


def test_batch_forward_allocates_distinct_ports_and_skips_invalid_nodes(
    client: TestClient,
) -> None:
    """批量转发应为有效外部节点分配不同端口，并返回单项失败原因。"""

    headers = _headers(client)
    server = client.post("/api/three-xui/servers", json=_server_payload(), headers=headers)
    assert server.status_code == 201
    first = client.post(
        "/api/nodes",
        json={
            "name": "批量节点一",
            "type": "vless",
            "server": "batch-one.example.test",
            "port": 443,
            "uuid": "00000000-0000-4000-0000-000000000411",
        },
        headers=headers,
    )
    second = client.post(
        "/api/nodes",
        json={
            "name": "批量节点二",
            "type": "vless",
            "server": "batch-two.example.test",
            "port": 443,
            "uuid": "00000000-0000-4000-0000-000000000412",
        },
        headers=headers,
    )
    assert first.status_code == 201 and second.status_code == 201
    response = client.post(
        "/api/three-xui/forward/batch",
        json={
            "source_node_ids": [first.json()["id"], second.json()["id"], 999999],
            "target_server_id": server.json()["id"],
            "listen_port_start": 25000,
            "listen_port_end": 25010,
        },
        headers=headers,
    )
    assert response.status_code == 202
    body = response.json()
    assert [task["listen_port"] for task in body["tasks"]] == [25000, 25001]
    assert body["skipped"] == [{"source_node_id": 999999, "reason": "源节点不存在"}]
