"""本地 TTL 缓存封装与跨进程失效版本。"""

from __future__ import annotations

import threading
from typing import Any

from cachetools import TTLCache

from app.core.config import get_settings
from app.core.coordination import shared_cache_versions


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
        """清空本地缓存，并推进共享版本使其他 worker 的旧键失效。"""

        with self._lock:
            self._cache.clear()
        shared_cache_versions.bump("global")

    def reconfigure(self, ttl_seconds: int) -> None:
        """按新 TTL 重建缓存，旧缓存立即失效。"""

        with self._lock:
            self._cache = TTLCache(maxsize=1024, ttl=ttl_seconds)
        shared_cache_versions.bump("global")

    def delete_prefix(self, prefix: str) -> None:
        """删除指定业务前缀的缓存，不影响其他套餐。"""

        with self._lock:
            for key in list(self._cache):
                if key.startswith(prefix):
                    self._cache.pop(key, None)

    def bump_version(self, namespace: str) -> int:
        """递增业务版本，用于缓存键隔离并避免旧值复用。"""

        version = shared_cache_versions.bump(namespace)
        with self._lock:
            self._versions[namespace] = version
        return version

    def version(self, namespace: str) -> int:
        """读取共享业务版本，使其他 worker 的失效操作立即可见。"""

        version = shared_cache_versions.get(namespace)
        with self._lock:
            self._versions[namespace] = version
        return version


cache_service = CacheService()
