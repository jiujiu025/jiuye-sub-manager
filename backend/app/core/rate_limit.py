"""基于数据库的跨进程请求限流。"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db import engine
from app.models.runtime import RateLimitEvent

RATE_LIMIT_MESSAGE = "请求过于频繁，请稍后再试"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int
    reservation_id: int | None = None


class InMemoryRateLimiter:
    """固定时间窗口限流器，数据库可用时在多个 worker 间共享。"""

    def __init__(self, max_keys: int = 10000) -> None:
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.RLock()

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        """只检查当前窗口，不占用名额；保留给兼容调用方。"""

        if limit <= 0 or window_seconds <= 0:
            return RateLimitDecision(True, 0)
        now = time.time()
        try:
            with engine.begin() as connection:
                self._purge_db(connection, key, now, window_seconds)
                count, oldest = self._db_count(connection, key)
            return self._decision(count, oldest, limit, now, window_seconds)
        except SQLAlchemyError:
            return self._local_check(key, limit, window_seconds)

    def reserve(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        """原子检查并占用一次请求名额，适用于多进程入口。"""

        if limit <= 0 or window_seconds <= 0:
            return RateLimitDecision(True, 0)
        now = time.time()
        try:
            with engine.begin() as connection:
                self._purge_db(connection, key, now, window_seconds)
                count, oldest = self._db_count(connection, key)
                decision = self._decision(count, oldest, limit, now, window_seconds)
                if not decision.allowed:
                    return decision
                result = connection.execute(
                    insert(RateLimitEvent).values(rate_key=key, occurred_at=now)
                )
                reservation_id = result.inserted_primary_key[0]
                return RateLimitDecision(True, 0, int(reservation_id))
        except SQLAlchemyError:
            return self._local_reserve(key, limit, window_seconds)

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        """记录一次请求或失败尝试，兼容旧调用方。"""

        if limit <= 0 or window_seconds <= 0:
            return
        now = time.time()
        try:
            with engine.begin() as connection:
                self._purge_db(connection, key, now, window_seconds)
                connection.execute(
                    insert(RateLimitEvent).values(rate_key=key, occurred_at=now)
                )
            return
        except SQLAlchemyError:
            pass
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
        """清除指定键的失败计数。"""

        try:
            with engine.begin() as connection:
                connection.execute(
                    delete(RateLimitEvent).where(RateLimitEvent.rate_key == key)
                )
        except SQLAlchemyError:
            pass

        with self._lock:
            self._events.pop(key, None)

    def release(self, reservation_id: int | None) -> None:
        """释放登录成功对应的单次占用，不影响并发请求的失败计数。"""

        if reservation_id is None:
            return
        try:
            with engine.begin() as connection:
                connection.execute(
                    delete(RateLimitEvent).where(RateLimitEvent.id == reservation_id)
                )
        except SQLAlchemyError:
            logger.debug("释放限流占用失败", exc_info=True)

    def clear_all(self) -> None:
        """测试和运维重载时清空共享窗口。"""

        try:
            with engine.begin() as connection:
                connection.execute(delete(RateLimitEvent))
        except SQLAlchemyError:
            pass

        with self._lock:
            self._events.clear()

    @staticmethod
    def _purge(events: deque[float], now: float, window_seconds: int) -> None:
        threshold = now - window_seconds
        while events and events[0] <= threshold:
            events.popleft()

    @staticmethod
    def _purge_db(connection, key: str, now: float, window_seconds: int) -> None:
        connection.execute(
            delete(RateLimitEvent).where(
                RateLimitEvent.rate_key == key,
                RateLimitEvent.occurred_at <= now - window_seconds,
            )
        )

    @staticmethod
    def _db_count(connection, key: str) -> tuple[int, float | None]:
        count = int(
            connection.scalar(
                select(func.count()).select_from(RateLimitEvent).where(
                    RateLimitEvent.rate_key == key
                )
            )
            or 0
        )
        oldest = connection.scalar(
            select(func.min(RateLimitEvent.occurred_at)).where(
                RateLimitEvent.rate_key == key
            )
        )
        return count, float(oldest) if oldest is not None else None

    @staticmethod
    def _decision(
        count: int,
        oldest: float | None,
        limit: int,
        now: float,
        window_seconds: int,
    ) -> RateLimitDecision:
        if count < limit or oldest is None:
            return RateLimitDecision(True, 0)
        retry_after = max(1, int(oldest + window_seconds - now + 0.999))
        return RateLimitDecision(False, retry_after)

    def _local_check(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        now = time.monotonic()
        with self._lock:
            events = self._events.get(key)
            if events is None:
                return RateLimitDecision(True, 0)
            self._purge(events, now, window_seconds)
            if not events:
                self._events.pop(key, None)
                return RateLimitDecision(True, 0)
            return self._decision(len(events), events[0], limit, now, window_seconds)

    def _local_reserve(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        decision = self._local_check(key, limit, window_seconds)
        if decision.allowed:
            self._local_hit(key, window_seconds)
        return decision

    def _local_hit(self, key: str, window_seconds: int) -> None:
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
