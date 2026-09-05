"""pytest 公共 fixture：隔离测试数据库与应用客户端。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 让测试可以导入 scripts/ 下的备份恢复工具
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

# 必须在导入 app 前设置测试环境变量，确保使用独立数据库
_tmp_dir = tempfile.mkdtemp(prefix="sub_manager_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir, 'test.db').as_posix()}"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "TestPass123!"
os.environ["CORS_ORIGINS"] = "*"
os.environ["SYNC_ENABLED"] = "false"

from app.main import app  # noqa: E402
from app.db import engine  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.core.rate_limit import rate_limiter  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    """返回触发应用启动生命周期的事件循环客户端。"""

    # 测试库直接建表，不依赖 Alembic 迁移
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def mock_upstream_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """为 FakeClient 测试提供固定公网解析，避免依赖测试机外网 DNS。"""

    monkeypatch.setattr(
        "app.services.sync_service.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )


@pytest.fixture(autouse=True)
def reset_rate_limits() -> None:
    """隔离测试之间的进程内限流状态。"""

    rate_limiter.clear_all()
    yield
    rate_limiter.clear_all()
