"""定时同步任务调度。"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import SessionLocal
from app.services.settings_service import SettingsService
from app.services.sync_service import SyncService

logger = logging.getLogger(__name__)


class SyncScheduler:
    """基于 APScheduler 的进程内定时同步。"""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone="UTC")

    def start(self) -> None:
        db = SessionLocal()
        try:
            runtime = SettingsService(db).get()
        finally:
            db.close()
        self.apply_runtime_settings(runtime.sync_enabled, runtime.sync_interval_minutes)
        if not self.scheduler.running:
            self.scheduler.start()
        if runtime.sync_enabled and runtime.sync_interval_minutes > 0:
            logger.info(
                "定时同步任务已启动，间隔 %s 分钟", runtime.sync_interval_minutes
            )
        else:
            logger.info("定时同步已禁用")

    def apply_runtime_settings(
        self, sync_enabled: bool, interval_minutes: int
    ) -> None:
        """动态调整定时任务；修改后立即生效。"""

        job = self.scheduler.get_job("sync_all_sources")
        if sync_enabled and interval_minutes > 0:
            if job is not None:
                job.modify(trigger=IntervalTrigger(minutes=interval_minutes))
            else:
                self.scheduler.add_job(
                    self.run_all,
                    trigger=IntervalTrigger(minutes=interval_minutes),
                    id="sync_all_sources",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
        elif job is not None:
            job.remove()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def run_all(self) -> None:
        db = SessionLocal()
        service = SyncService(db)
        try:
            results = service.sync_all_enabled()
            failed = [r.source_name for r in results if r.status == "failed"]
            if failed:
                logger.warning("本次定时同步失败来源：%s", ", ".join(failed))
        finally:
            service.client.close()
            db.close()


scheduler = SyncScheduler()
