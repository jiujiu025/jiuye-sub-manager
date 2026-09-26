"""套餐具体节点选择 node_ids 功能测试。"""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.node import Node
from app.models.package import Package, PackageRule
from app.models.user import User
from app.schemas.package import PackageCreate
from app.services.package_service import PackageService
from app.services.subscription_service import SubscriptionService
from app.utils.fingerprint import build_node_fingerprint


def _add_node(
    db,
    *,
    name: str,
    server: str,
    uuid: str,
    source_name: str,
    country: str = "香港",
    enabled: bool = True,
) -> Node:
    node = Node(
        source_id=None,
        source_name=source_name,
        original_name=name,
        name=name,
        type="vless",
        server=server,
        port=443,
        uuid=uuid,
        country=country,
        enabled=enabled,
        source_type="custom" if source_name == "自有节点" else "upstream",
        node_fingerprint=build_node_fingerprint(
            node_type="vless", server=server, port=443, uuid=uuid
        ),
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _admin(db) -> User:
    return db.scalar(select(User).where(User.username == "admin"))


def _preview_names(service: PackageService, package) -> list[str]:
    return [node.name for node in service.preview(package)]


@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_legacy_package_without_node_ids(db_session) -> None:
    """旧套餐 node_ids 为 NULL 时行为与原来一致。"""

    source_node = _add_node(
        db_session,
        name="源A香港",
        server="legacy-a.example.com",
        uuid="legacy-a",
        source_name="nodeids源A",
    )
    _add_node(
        db_session,
        name="自有香港",
        server="legacy-self.example.com",
        uuid="legacy-self",
        source_name="自有节点",
    )

    package = Package(
        name="nodeids旧套餐",
        enabled=True,
        token_hash="legacy-hash",
        token_prefix="legacy",
    )
    db_session.add(package)
    db_session.flush()
    db_session.add(
        PackageRule(
            package=package,
            source_filter=["nodeids源A"],
            node_ids=None,
        )
    )
    db_session.commit()

    service = PackageService(db_session)
    assert _preview_names(service, package) == ["源A香港"]


def test_source_filter_only(db_session) -> None:
    """只选择订阅源时正常。"""

    _add_node(
        db_session,
        name="源A日本",
        server="source-a.example.com",
        uuid="source-a",
        source_name="nodeids源B",
        country="日本",
    )
    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="nodeids来源套餐",
            rules={"source_filter": ["nodeids源B"]},
        ),
        _admin(db_session),
    )
    assert _preview_names(service, package) == ["源A日本"]


def test_single_self_node(db_session) -> None:
    """只选择一个自有节点时只出现该节点。"""

    self_one = _add_node(
        db_session,
        name="自有美国01",
        server="self-one.example.com",
        uuid="self-one",
        source_name="自有节点",
        country="美国",
    )
    _add_node(
        db_session,
        name="自有香港01",
        server="self-hk.example.com",
        uuid="self-hk",
        source_name="自有节点",
    )
    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="nodeids单自有套餐",
            rules={"node_ids": [self_one.id]},
        ),
        _admin(db_session),
    )
    assert _preview_names(service, package) == ["自有美国01"]


def test_multiple_self_nodes(db_session) -> None:
    """选择多个自有节点时都出现。"""

    first = _add_node(
        db_session,
        name="自有美国02",
        server="self-two-a.example.com",
        uuid="self-two-a",
        source_name="自有节点",
        country="美国",
    )
    second = _add_node(
        db_session,
        name="自有日本02",
        server="self-two-b.example.com",
        uuid="self-two-b",
        source_name="自有节点",
        country="日本",
    )
    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="nodeids多自有套餐",
            rules={"node_ids": [first.id, second.id]},
        ),
        _admin(db_session),
    )
    assert sorted(_preview_names(service, package)) == ["自有日本02", "自有美国02"]


def test_source_plus_self_nodes(db_session) -> None:
    """订阅源与自有节点同时出现。"""

    _add_node(
        db_session,
        name="源C美国",
        server="source-c.example.com",
        uuid="source-c",
        source_name="nodeids源C",
        country="美国",
    )
    self_node = _add_node(
        db_session,
        name="自有美国03",
        server="self-three.example.com",
        uuid="self-three",
        source_name="自有节点",
        country="美国",
    )
    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="nodeids混合套餐",
            rules={
                "source_filter": ["nodeids源C"],
                "node_ids": [self_node.id],
            },
        ),
        _admin(db_session),
    )
    assert sorted(_preview_names(service, package)) == ["源C美国", "自有美国03"]


def test_same_node_via_source_and_node_ids_once(db_session) -> None:
    """同一节点同时被来源和 node_ids 命中时只出现一次。"""

    node = _add_node(
        db_session,
        name="源D节点",
        server="source-d.example.com",
        uuid="source-d",
        source_name="nodeids源D",
    )
    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="nodeids去重套餐",
            rules={
                "source_filter": ["nodeids源D"],
                "node_ids": [node.id],
            },
        ),
        _admin(db_session),
    )
    assert _preview_names(service, package) == ["源D节点"]


def test_missing_node_ids_ignored(db_session) -> None:
    """node_ids 包含不存在的 ID 时忽略且不报错。"""

    _add_node(
        db_session,
        name="源E节点",
        server="source-e.example.com",
        uuid="source-e",
        source_name="nodeids源E",
    )
    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="nodeids缺失套餐",
            rules={
                "source_filter": ["nodeids源E"],
                "node_ids": [999999],
            },
        ),
        _admin(db_session),
    )
    assert _preview_names(service, package) == ["源E节点"]


def test_disabled_self_node_excluded(db_session) -> None:
    """禁用节点即使被 node_ids 选中也不出现。"""

    disabled = _add_node(
        db_session,
        name="自有禁用节点",
        server="self-disabled.example.com",
        uuid="self-disabled",
        source_name="自有节点",
        enabled=False,
    )
    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="nodeids禁用套餐",
            rules={"node_ids": [disabled.id]},
        ),
        _admin(db_session),
    )
    assert _preview_names(service, package) == []


def test_filters_and_rules_still_apply(db_session) -> None:
    """国家/类型/关键词/重命名/排序仍对两类节点统一生效。"""

    _add_node(
        db_session,
        name="美国线路01",
        server="rule-source.example.com",
        uuid="rule-source",
        source_name="nodeids规则源",
        country="美国",
    )
    self_hk = _add_node(
        db_session,
        name="香港自有01",
        server="rule-self-hk.example.com",
        uuid="rule-self-hk",
        source_name="自有节点",
        country="香港",
    )
    self_us = _add_node(
        db_session,
        name="美国自有01",
        server="rule-self-us.example.com",
        uuid="rule-self-us",
        source_name="自有节点",
        country="美国",
    )
    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="nodeids规则套餐",
            rules={
                "source_filter": ["nodeids规则源"],
                "node_ids": [self_hk.id, self_us.id],
                "country_filter": ["美国"],
                "type_filter": ["vless"],
                "include_keywords": ["美国"],
                "exclude_keywords": ["香港"],
                "rename_rules": [
                    {"replacements": [{"from": "美国", "to": "US"}]}
                ],
                "sort_rules": [{"field": "name", "direction": "asc"}],
            },
        ),
        _admin(db_session),
    )
    names = _preview_names(service, package)
    assert names == ["US线路01", "US自有01"]


def test_preview_matches_subscription_output(db_session) -> None:
    """预览与 /sub 实际输出使用同一规则。"""

    self_node = _add_node(
        db_session,
        name="自有新加坡01",
        server="match-self.example.com",
        uuid="match-self",
        source_name="自有节点",
        country="新加坡",
    )
    service = PackageService(db_session)
    package, token = service.create(
        PackageCreate(
            name="nodeids一致套餐",
            rules={"node_ids": [self_node.id]},
        ),
        _admin(db_session),
    )
    preview = service.preview(package)
    assert [node.name for node in preview] == ["自有新加坡01"]

    yaml_text, _ = SubscriptionService(db_session).generate_clash(package)
    data = yaml.safe_load(yaml_text)
    proxy_names = [proxy["name"] for proxy in data["proxies"]]
    assert proxy_names == ["自有新加坡01"]


def test_package_api_saves_and_returns_node_ids(
    client: TestClient, auth_headers: dict
) -> None:
    """创建/编辑/查询套餐应正确保存与返回 node_ids。"""

    db = SessionLocal()
    try:
        node = _add_node(
            db,
            name="API自有节点",
            server="api-self.example.com",
            uuid="api-self",
            source_name="自有节点",
        )
        node_id = node.id
    finally:
        db.close()

    create = client.post(
        "/api/packages",
        headers=auth_headers,
        json={
            "name": "nodeids API 套餐",
            "rules": {"node_ids": [node_id]},
        },
    )
    assert create.status_code == 201
    package_id = create.json()["id"]

    detail = client.get(f"/api/packages/{package_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["rules"]["node_ids"] == [node_id]

    updated = client.put(
        f"/api/packages/{package_id}",
        headers=auth_headers,
        json={"rules": {"node_ids": []}},
    )
    assert updated.status_code == 200
    assert updated.json()["rules"]["node_ids"] == []


def test_deleting_node_cleans_package_node_ids(db_session) -> None:
    """删除节点时必须同步清理套餐中的节点 ID，避免后续 ID 复用串套餐。"""

    node = _add_node(
        db_session,
        name="待删除节点",
        server="delete-node.example.com",
        uuid="delete-node-uuid",
        source_name="自有节点",
    )
    package_service = PackageService(db_session)
    package, _ = package_service.create(
        PackageCreate(name="删除节点清理套餐", rules={"node_ids": [node.id]}),
        _admin(db_session),
    )

    from app.services.node_service import NodeService

    NodeService(db_session).delete(node, _admin(db_session))
    db_session.expire_all()
    rule = db_session.scalar(
        select(PackageRule).where(PackageRule.package_id == package.id)
    )
    assert rule is not None
    assert rule.node_ids == []
