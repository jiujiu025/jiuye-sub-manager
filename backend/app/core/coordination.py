"""基于现有数据库的跨进程运行时协调能力。"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db import engine
from app.models.runtime import CacheNamespaceVersion, SchedulerLease

logger = logging.getLogger(__name__)


class SharedCacheVersionStore:
    """通过数据库共享缓存失效版本，不把订阅正文写入数据库。"""

    def __init__(self) -> None:
        self._fallback_versions: dict[str, int] = {}

    def get(self, namespace: str) -> int:
        try:
            with engine.connect() as connection:
                value = connection.scalar(
                    select(CacheNamespaceVersion.version).where(
                        CacheNamespaceVersion.namespace == namespace
                    )
                )
            if value is None:
                return self._fallback_versions.get(namespace, 0)
            version = int(value)
            self._fallback_versions[namespace] = max(
                version, self._fallback_versions.get(namespace, 0)
            )
            return version
        except SQLAlchemyError:
            # 迁移尚未完成时保留单进程降级能力，避免启动阶段阻断健康检查。
            return self._fallback_versions.get(namespace, 0)

    def bump(self, namespace: str) -> int:
        now = time.time()
        try:
            with engine.begin() as connection:
                result = connection.execute(
                    update(CacheNamespaceVersion)
                    .where(CacheNamespaceVersion.namespace == namespace)
                    .values(
                        version=CacheNamespaceVersion.version + 1,
                        updated_at=now,
                    )
                )
                if result.rowcount:
                    version = connection.scalar(
                        select(CacheNamespaceVersion.version).where(
                            CacheNamespaceVersion.namespace == namespace
                        )
                    )
                    self._fallback_versions[namespace] = int(version)
                    return int(version)
                connection.execute(
                    insert(CacheNamespaceVersion).values(
                        namespace=namespace,
                        version=1,
                        updated_at=now,
                    )
                )
                self._fallback_versions[namespace] = 1
                return 1
        except IntegrityError:
            # 两个 worker 同时首次创建命名空间时，竞争者读取已提交版本。
            version = self.get(namespace)
            if version:
                return version
        except SQLAlchemyError:
            pass

        version = self._fallback_versions.get(namespace, 0) + 1
        self._fallback_versions[namespace] = version
        return version


class SchedulerLeaseStore:
    """使用数据库租约协调 APScheduler 的重复触发。"""

    def __init__(self, owner_id: str | None = None) -> None:
        self.owner_id = owner_id or uuid.uuid4().hex

    def try_acquire(self, job_name: str, lease_seconds: int) -> bool:
        now = time.time()
        until = now + max(1, lease_seconds)
        try:
            with engine.begin() as connection:
                result = connection.execute(
                    update(SchedulerLease)
                    .where(
                        SchedulerLease.job_name == job_name,
                        (SchedulerLease.lease_until <= now)
                        | (SchedulerLease.owner_id == self.owner_id),
                    )
                    .values(
                        owner_id=self.owner_id,
                        lease_until=until,
                        updated_at=now,
                    )
                )
                if result.rowcount:
                    return True
                connection.execute(
                    insert(SchedulerLease).values(
                        job_name=job_name,
                        owner_id=self.owner_id,
                        lease_until=until,
                        updated_at=now,
                    )
                )
                return True
        except IntegrityError:
            return False
        except SQLAlchemyError:
            # 迁移未完成或数据库短暂不可用时不阻断业务任务。
            logger.exception("任务 %s 获取共享租约失败，将按单进程方式执行", job_name)
            return True

    def release(self, job_name: str) -> None:
        try:
            with engine.begin() as connection:
                connection.execute(
                    delete(SchedulerLease).where(
                        SchedulerLease.job_name == job_name,
                        SchedulerLease.owner_id == self.owner_id,
                    )
                )
        except SQLAlchemyError:
            logger.warning("任务 %s 释放共享租约失败", job_name, exc_info=True)


shared_cache_versions = SharedCacheVersionStore()
