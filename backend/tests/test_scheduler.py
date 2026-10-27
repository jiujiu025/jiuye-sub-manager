"""定时同步资源释放测试。"""

from __future__ import annotations

from types import SimpleNamespace

from app.tasks import scheduler as scheduler_module


def test_scheduler_closes_sync_client_and_database(monkeypatch) -> None:
    """定时同步结束后必须关闭 HTTP 客户端和数据库会话。"""

    db = SimpleNamespace(closed=False)
    client = SimpleNamespace(closed=False)

    def close_db() -> None:
        db.closed = True

    def close_client() -> None:
        client.closed = True

    db.close = close_db
    client.close = close_client
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db)

    class FakeSyncService:
        def __init__(self, session) -> None:
            assert session is db
            self.client = client

        def sync_all_enabled(self):
            return [SimpleNamespace(source_name="测试来源", status="success")]

    monkeypatch.setattr(scheduler_module, "SyncService", FakeSyncService)

    scheduler_module.SyncScheduler().run_all()

    assert client.closed is True
    assert db.closed is True


def test_scheduler_health_checks_include_all_enabled_nodes(monkeypatch) -> None:
    """定时健康检测必须覆盖上游订阅节点和已转发节点。"""

    db = SimpleNamespace(closed=False)
    db.close = lambda: setattr(db, "closed", True)
    calls: list[bool] = []

    class FakeHealthService:
        def __init__(self, session) -> None:
            assert session is db

        def run_all(self, *, include_all: bool = False) -> int:
            calls.append(include_all)
            return 0

    class FakeLeaseStore:
        def try_acquire(self, key: str, ttl: int) -> bool:
            return True

        def release(self, key: str) -> None:
            pass

    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(scheduler_module, "NodeHealthService", FakeHealthService)

    scheduler = scheduler_module.SyncScheduler()
    scheduler.lease_store = FakeLeaseStore()
    scheduler.run_health_checks()

    assert calls == [True]
    assert db.closed is True
