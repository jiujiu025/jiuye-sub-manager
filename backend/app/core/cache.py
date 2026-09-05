"""进程内 TTL 缓存封装，后续可替换为 Redis 实现。"""

from __future__ import annotations

import threading
from typing import Any

from cachetools import TTLCache

from app.core.config import get_settings


class CacheService:
    """带默认 TTL 的进程内缓存。"""

    def __init__(self, ttl_seconds: int | None = None, maxsize: int = 1024) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else get_settings().cache_ttl_seconds
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()
        self._versions: dict[str, int] = {}

    def get(self, key: str) -> Any | None:
        """读取缓存，不存在或已过期时返回 None。"""

        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """写入缓存。"""

        with self._lock:
            self._cache[key] = value

    def delete(self, key: str) -> None:
        """删除单个缓存键。"""

        with self._lock:
            self._cache.pop(key, None)

    def invalidate_all(self) -> None:
        """清空全部缓存。"""

        with self._lock:
            self._cache.clear()

    def reconfigure(self, ttl_seconds: int) -> None:
        """按新 TTL 重建缓存，旧缓存立即失效。"""

        with self._lock:
            self._cache = TTLCache(maxsize=1024, ttl=ttl_seconds)

    def delete_prefix(self, prefix: str) -> None:
        """删除指定业务前缀的缓存，不影响其他套餐。"""

        with self._lock:
            for key in list(self._cache):
                if key.startswith(prefix):
                    self._cache.pop(key, None)

    def bump_version(self, namespace: str) -> int:
        """递增业务版本，用于缓存键隔离并避免旧值复用。"""

        with self._lock:
            version = self._versions.get(namespace, 0) + 1
            self._versions[namespace] = version
            return version

    def version(self, namespace: str) -> int:
        """读取业务版本；进程重启后缓存和版本一起自然失效。"""

        with self._lock:
            return self._versions.get(namespace, 0)


cache_service = CacheService()
