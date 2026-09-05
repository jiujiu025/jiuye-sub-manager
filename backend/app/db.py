"""数据库引擎与会话管理。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _ensure_sqlite_parent(database_url: str) -> None:
    """SQLite 文件所在目录不存在时自动创建。"""

    if not database_url.startswith("sqlite:///"):
        return
    db_path = database_url.removeprefix("sqlite:///")
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent(settings.database_url)

_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        """启用 WAL 与外键约束，提升并发与数据完整性。"""

        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：提供数据库会话。"""

    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
