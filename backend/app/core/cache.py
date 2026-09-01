"""进程内 TTL 缓存封装，后续可替换为 Redis 实现。"""

from __future__ import annotations

from typing import Any

from cachetools import TTLCache

from app.core.config import get_settings


class CacheService:
    """带默认 TTL 的进程内缓存。"""

    def __init__(self, ttl_seconds: int | None = None, maxsize: int = 1024) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else get_settings().cache_ttl_seconds
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=maxsize, ttl=ttl)

    def get(self, key: str) -> Any | None:
        """读取缓存，不存在或已过期时返回 None。"""

        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """写入缓存。"""

        self._cache[key] = value

    def delete(self, key: str) -> None:
        """删除单个缓存键。"""

        self._cache.pop(key, None)

    def invalidate_all(self) -> None:
        """清空全部缓存。"""

        self._cache.clear()

    def reconfigure(self, ttl_seconds: int) -> None:
        """按新 TTL 重建缓存，旧缓存立即失效。"""

        self._cache = TTLCache(maxsize=1024, ttl=ttl_seconds)


cache_service = CacheService()
