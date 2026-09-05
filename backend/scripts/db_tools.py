"""SQLite 数据库备份/恢复公共工具（Windows/Linux 通用）。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


def resolve_sqlite_path(database_url: str) -> Path:
    """从 DATABASE_URL 中解析 SQLite 文件路径。"""

    if not database_url.startswith("sqlite:///"):
        raise SystemExit("当前仅支持 SQLite 数据库")
    raw = database_url.removeprefix("sqlite:///")
    if raw == ":memory:":
        raise SystemExit("内存数据库无法备份")
    return Path(raw).resolve()


def backup_database(db_path: Path) -> Path:
    """使用 SQLite 在线备份 API 生成带时间戳的一致快照。"""

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest_path = backup_dir / f"sub_manager_{stamp}.db"
    counter = 1
    while dest_path.exists():
        dest_path = backup_dir / f"sub_manager_{stamp}_{counter}.db"
        counter += 1
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(dest_path))
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    return dest_path


def restore_database(db_path: Path, backup_file: Path) -> Path:
    """恢复前先自动备份当前数据库，再把备份内容写回目标库。"""

    if not backup_file.exists():
        raise SystemExit(f"备份文件不存在：{backup_file}")
    pre_restore_backup = backup_database(db_path)
    src = sqlite3.connect(str(backup_file))
    try:
        dst = sqlite3.connect(str(db_path))
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    return pre_restore_backup
