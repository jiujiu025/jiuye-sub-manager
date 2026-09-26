"""进程内请求限流；保持单体部署可用，后续可替换为共享存储实现。"""

from __future__ import annotations

import hashlib
import ipaddress
import threading
import time
from collections import deque
from dataclasses import dataclass

from fastapi import Request

from app.core.config import get_settings

RATE_LIMIT_MESSAGE = "请求过于频繁，请稍后再试"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int


class InMemoryRateLimiter:
    """固定时间窗口限流器，带上限和锁，避免进程内并发访问 TTLCache 风格问题。"""

    def __init__(self, max_keys: int = 10000) -> None:
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.RLock()

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        """检查当前窗口是否仍可请求，不会增加计数。"""

        if limit <= 0 or window_seconds <= 0:
            return RateLimitDecision(True, 0)
        now = time.monotonic()
        with self._lock:
            events = self._events.get(key)
            if events is None:
                return RateLimitDecision(True, 0)
            self._purge(events, now, window_seconds)
            if not events:
                self._events.pop(key, None)
                return RateLimitDecision(True, 0)
            if len(events) < limit:
                return RateLimitDecision(True, 0)
            retry_after = max(1, int(events[0] + window_seconds - now + 0.999))
            return RateLimitDecision(False, retry_after)

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        """记录一次请求或失败尝试。"""

        if limit <= 0 or window_seconds <= 0:
            return
        now = time.monotonic()
        with self._lock:
            if key not in self._events and len(self._events) >= self.max_keys:
                oldest_key = min(
                    self._events,
                    key=lambda item: self._events[item][-1] if self._events[item] else now,
                )
                self._events.pop(oldest_key, None)
            events = self._events.setdefault(key, deque())
            self._purge(events, now, window_seconds)
            events.append(now)

    def clear(self, key: str) -> None:
        """清除成功认证后的失败计数。"""

        with self._lock:
            self._events.pop(key, None)

    def clear_all(self) -> None:
        """测试和进程重载时清空窗口。"""

        with self._lock:
            self._events.clear()

    @staticmethod
    def _purge(events: deque[float], now: float, window_seconds: int) -> None:
        threshold = now - window_seconds
        while events and events[0] <= threshold:
            events.popleft()


rate_limiter = InMemoryRateLimiter()


def request_client_ip(request: Request) -> str:
    """获取客户端 IP；只有来自配置可信代理时才采信转发头。"""

    peer = request.client.host if request.client else "unknown"
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return peer

    trusted = []
    for raw_network in get_settings().trusted_proxy_cidrs.split(","):
        try:
            trusted.append(ipaddress.ip_network(raw_network.strip(), strict=False))
        except ValueError:
            continue
    if not any(peer_address in network for network in trusted):
        return peer

    forwarded = request.headers.get("x-real-ip")
    if forwarded:
        try:
            return str(ipaddress.ip_address(forwarded.strip()))
        except ValueError:
            pass
    return peer


def stable_rate_key(prefix: str, *parts: str) -> str:
    """对限流键做哈希，避免内存键暴露 Token 或用户名。"""

    raw = "\x00".join((prefix, *parts))
    return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"
