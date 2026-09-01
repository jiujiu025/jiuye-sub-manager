"""日志初始化与敏感信息脱敏。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class SensitiveFilter(logging.Filter):
    """过滤包含敏感关键字的事件，防止 UUID、密码、Token 写入日志。"""

    SENSITIVE_KEYWORDS = (
        "password",
        "token",
        "uuid",
        "vless://",
        "ss://",
        "shadow",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        return not any(keyword in message for keyword in self.SENSITIVE_KEYWORDS)


def setup_logging(level: int = logging.INFO) -> None:
    """配置控制台与滚动文件日志，并挂载敏感信息过滤器。"""

    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveFilter())
    root.setLevel(level)
    root.addHandler(handler)

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SensitiveFilter())
    root.addHandler(file_handler)
