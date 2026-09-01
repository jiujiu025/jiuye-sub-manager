"""读取应用日志文件尾部。"""

from __future__ import annotations

from collections import deque
from pathlib import Path


def read_log_tail(lines: int = 100, error_only: bool = False) -> list[str]:
    """读取 logs/app.log 最后若干行，可选只保留错误级别。"""

    log_path = Path("logs/app.log")
    if not log_path.exists():
        return []
    tail: deque[str] = deque(maxlen=max(lines, 1))
    with log_path.open("r", encoding="utf-8", errors="ignore") as log_file:
        for line in log_file:
            stripped = line.rstrip("\n")
            if error_only and not (
                "ERROR" in stripped or "CRITICAL" in stripped
            ):
                continue
            tail.append(stripped)
    return list(tail)
