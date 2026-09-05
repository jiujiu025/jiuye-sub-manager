"""日志初始化与敏感信息脱敏。"""

from __future__ import annotations

import logging
import re
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path


_URI_PATTERN = re.compile(
    r"(?i)\b(?:vless|vmess|ss|trojan)://[^\s\"'<>]+"
)
_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)\b(?:authorization\s*[:=]\s*|bearer\s+)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_URL_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(https?://)[^/@\s]+@"
)
_SUBSCRIPTION_PATH_PATTERN = re.compile(
    r"(?i)(/sub/)[^/?\s\"'<>]+"
)
_JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
)
_SENSITIVE_PARAMETER_PATTERN = re.compile(
    r"(?i)(\b(?:authorization|jwt_secret_key|access_token|subscription_token|token|password|passwd|secret|uuid|key|auth|public[-_]key|short[-_]id)\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s&,}]+)"
)


def redact_sensitive_text(text: str) -> str:
    """对日志文本中的凭据、节点 URI 和订阅 Token 做字段级脱敏。"""

    redacted = _URI_PATTERN.sub("[REDACTED_URI]", text)
    redacted = _AUTHORIZATION_PATTERN.sub("[REDACTED_AUTHORIZATION]", redacted)
    redacted = _URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED_CREDENTIALS]@", redacted)
    redacted = _SUBSCRIPTION_PATH_PATTERN.sub(r"\1[REDACTED_TOKEN]", redacted)

    def replace_parameter(match: re.Match[str]) -> str:
        value = match.group(2)
        if value[:1] in {'"', "'"} and value[-1:] == value[:1]:
            return f'{match.group(1)}{value[:1]}[REDACTED]{value[-1:]}'
        return f"{match.group(1)}[REDACTED]"

    redacted = _SENSITIVE_PARAMETER_PATTERN.sub(replace_parameter, redacted)
    return _JWT_PATTERN.sub("[REDACTED_JWT]", redacted)


class SensitiveFilter(logging.Filter):
    """保留日志事件，但移除密码、UUID、Token 等敏感值。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            exception_text = "".join(
                traceback.format_exception_only(record.exc_info[0], record.exc_info[1])
            )
            record.exc_text = redact_sensitive_text(exception_text)
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """配置控制台与滚动文件日志，并挂载敏感信息过滤器。"""

    root = logging.getLogger()
    sensitive_filter = SensitiveFilter()
    loggers = [root, logging.getLogger("uvicorn.access"), logging.getLogger("uvicorn.error")]
    if any(logger.handlers for logger in loggers):
        root.setLevel(level)
        for logger in loggers:
            for existing_handler in logger.handlers:
                if not any(isinstance(item, SensitiveFilter) for item in existing_handler.filters):
                    existing_handler.addFilter(sensitive_filter)
        return
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    handler.addFilter(sensitive_filter)
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
    file_handler.addFilter(sensitive_filter)
    root.addHandler(file_handler)
