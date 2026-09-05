"""SQLite 备份/恢复脚本测试。"""

from __future__ import annotations

import sqlite3

from db_tools import backup_database, restore_database


def _init_db(path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO demo (name) VALUES ('before')")
        conn.commit()
    finally:
        conn.close()


def _read_names(path) -> list[str]:
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute("SELECT name FROM demo ORDER BY id").fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def test_backup_and_restore(tmp_path) -> None:
    """备份应生成一致快照，恢复前自动再备份一次当前数据库。"""

    db_path = tmp_path / "demo.db"
    _init_db(db_path)

    backup_path = backup_database(db_path)
    assert backup_path.exists()
    assert backup_path.name.startswith("sub_manager_")

    # 破坏当前数据
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DELETE FROM demo")
        conn.commit()
    finally:
        conn.close()
    assert _read_names(db_path) == []

    # 恢复前应自动备份当前（空）数据库，再恢复历史备份
    pre_restore_backup = restore_database(db_path, backup_path)
    assert pre_restore_backup.exists()
    assert _read_names(db_path) == ["before"]
