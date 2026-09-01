"""备份 SQLite 数据库：python scripts/backup_db.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from db_tools import backup_database, resolve_sqlite_path  # noqa: E402


def main() -> None:
    db_path = resolve_sqlite_path(get_settings().database_url)
    backup_path = backup_database(db_path)
    print(f"备份完成：{backup_path}")


if __name__ == "__main__":
    main()
