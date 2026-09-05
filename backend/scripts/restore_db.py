"""恢复 SQLite 数据库：python scripts/restore_db.py <备份文件>"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from db_tools import resolve_sqlite_path, restore_database  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("用法：python scripts/restore_db.py <备份文件路径>")
    backup_file = Path(sys.argv[1]).resolve()
    db_path = resolve_sqlite_path(get_settings().database_url)
    print("提示：恢复前建议先停止 API 服务，避免数据库文件被占用")
    pre_backup = restore_database(db_path, backup_file)
    print(f"恢复前已自动备份当前数据库：{pre_backup}")
    print(f"恢复完成：{backup_file} -> {db_path}")


if __name__ == "__main__":
    main()
