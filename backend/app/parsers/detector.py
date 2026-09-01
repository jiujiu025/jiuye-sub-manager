"""订阅格式自动检测。"""

from __future__ import annotations

import base64
import re

_BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/=\s]+$")
_URI_SCHEMES = (
    "vless://",
    "vmess://",
    "ss://",
    "trojan://",
    "socks://",
    "socks5://",
    "http://",
    "https://",
    "hysteria://",
    "hysteria2://",
    "hy2://",
    "tuic://",
)


def _looks_like_base64(content: str) -> bool:
    return bool(_BASE64_PATTERN.match(content)) and len(content) >= 16


def decode_base64(value: str) -> str | None:
    """解码 Base64 内容，失败时返回 None。"""

    compact = "".join(value.split())
    try:
        padding = "=" * (-len(compact) % 4)
        raw = base64.b64decode(compact + padding)
        return raw.decode("utf-8", errors="ignore")
    except (ValueError, TypeError):
        return None


def detect_format(content: str) -> str:
    """根据内容特征识别订阅格式。"""

    stripped = content.strip()
    if not stripped:
        return "unknown"
    first_line = stripped.splitlines()[0].strip()
    if first_line.startswith(_URI_SCHEMES):
        return "uri"
    if "proxies:" in stripped or "proxy-providers:" in stripped:
        return "clash"
    if stripped.startswith("{") and "outbounds" in stripped:
        return "singbox"
    if _looks_like_base64(stripped):
        decoded = decode_base64(stripped)
        if decoded and any(scheme in decoded for scheme in _URI_SCHEMES):
            return "base64"
    return "unknown"


def detect_uri_type(content: str) -> str:
    """识别单行 URI 的协议类型，用于选择具体解析器。"""

    for line in content.strip().splitlines():
        if line.startswith("vless://"):
            return "vless"
        if line.startswith("ss://"):
            return "ss"
    return "unknown"
