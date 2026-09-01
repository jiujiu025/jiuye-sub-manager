"""套餐规则服务测试：筛选、关键词、重命名、编号、排序。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models.node import Node
from app.models.user import User
from app.schemas.package import PackageCreate
from app.services.package_service import PackageService
from app.utils.fingerprint import build_node_fingerprint


@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()


def _add_node(
    db,
    *,
    name: str,
    node_type: str,
    server: str,
    port: int,
    source_name: str,
    country: str,
    uuid: str | None = None,
    password: str | None = None,
) -> Node:
    fingerprint = build_node_fingerprint(
        node_type=node_type,
        server=server,
        port=port,
        uuid=uuid,
        password=password,
    )
    node = Node(
        source_id=None,
        source_name=source_name,
        original_name=name,
        name=name,
        type=node_type,
        server=server,
        port=port,
        uuid=uuid,
        password=password,
        country=country,
        node_fingerprint=fingerprint,
    )
    db.add(node)
    return node


def _admin(db) -> User:
    return db.scalar(select(User).where(User.username == "admin"))


def test_package_filter_and_keywords(db_session) -> None:
    """套餐规则应按来源/地区/类型/关键词动态筛选。"""

    _add_node(
        db_session,
        name="香港高速01",
        node_type="vless",
        server="hk1.example.com",
        port=443,
        source_name="机场筛选A",
        country="香港",
        uuid="uuid-1",
    )
    _add_node(
        db_session,
        name="日本东京01",
        node_type="vless",
        server="jp1.example.com",
        port=443,
        source_name="机场筛选A",
        country="日本",
        uuid="uuid-2",
    )
    _add_node(
        db_session,
        name="美国01",
        node_type="shadowsocks",
        server="us1.example.com",
        port=8388,
        source_name="机场筛选A",
        country="美国",
        password="pass",
    )
    db_session.commit()

    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="筛选套餐",
            rules={
                "source_filter": ["机场筛选A"],
                "country_filter": ["香港"],
                "type_filter": ["vless"],
                "include_keywords": ["高速"],
            },
        ),
        _admin(db_session),
    )
    preview = service.preview(package)
    assert len(preview) == 1
    assert preview[0].name == "香港高速01"

    package.rules.include_keywords = []
    package.rules.exclude_keywords = ["高速"]
    db_session.commit()
    preview = service.preview(package)
    assert len(preview) == 0


def test_package_rename_and_numbering(db_session) -> None:
    """重命名规则应支持替换、国家缩写与按地区编号。"""

    _add_node(
        db_session,
        name="香港 高速 01",
        node_type="vless",
        server="hk1.example.com",
        port=443,
        source_name="机场重命名A",
        country="香港",
        uuid="uuid-a",
    )
    _add_node(
        db_session,
        name="香港 IEPL 02",
        node_type="vless",
        server="hk2.example.com",
        port=443,
        source_name="机场重命名A",
        country="香港",
        uuid="uuid-b",
    )
    _add_node(
        db_session,
        name="日本东京01",
        node_type="vless",
        server="jp1.example.com",
        port=443,
        source_name="机场重命名A",
        country="日本",
        uuid="uuid-c",
    )
    db_session.commit()

    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="重命名套餐",
            rules={
                "source_filter": ["机场重命名A"],
                "rename_rules": [
                    {
                        "replacements": [
                            {"from": "高速", "to": ""},
                            {"from": "IEPL", "to": ""},
                        ],
                        "country_abbr": True,
                        "numbered": True,
                    }
                ]
            },
        ),
        _admin(db_session),
    )
    preview = service.preview(package)
    assert [node.name for node in preview] == ["HK-01", "HK-02", "JP-01"]


def test_package_sort_rules(db_session) -> None:
    """排序规则应按自定义顺序排列。"""

    _add_node(
        db_session,
        name="日本01",
        node_type="vless",
        server="jp1.example.com",
        port=443,
        source_name="机场排序A",
        country="日本",
        uuid="uuid-jp",
    )
    _add_node(
        db_session,
        name="香港01",
        node_type="vless",
        server="hk1.example.com",
        port=443,
        source_name="机场排序A",
        country="香港",
        uuid="uuid-hk",
    )
    db_session.commit()

    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="排序套餐",
            rules={
                "source_filter": ["机场排序A"],
                "sort_rules": [{"field": "country", "order": ["香港", "日本"]}],
            },
        ),
        _admin(db_session),
    )
    preview = service.preview(package)
    assert [node.country for node in preview] == ["香港", "日本"]


def test_package_preview_empty_returns_empty_list(db_session) -> None:
    """无节点时应返回空列表而不是错误。"""

    service = PackageService(db_session)
    package, _ = service.create(
        PackageCreate(
            name="空套餐",
            rules={"source_filter": ["不存在的来源"]},
        ),
        _admin(db_session),
    )
    assert service.preview(package) == []
