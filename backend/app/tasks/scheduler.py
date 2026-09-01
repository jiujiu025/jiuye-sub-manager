"""定时同步任务调度。"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.sync_service import SyncService

logger = logging.getLogger(__name__)


class SyncScheduler:
    """基于 APScheduler 的进程内定时同步。"""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone="UTC")

    def start(self) -> None:
        interval = get_settings().sync_interval_minutes
        if interval <= 0:
            logger.info("同步间隔配置为 0，定时同步已禁用")
            return
        self.scheduler.add_job(
            self.run_all,
            trigger=IntervalTrigger(minutes=interval),
            id="sync_all_sources",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        logger.info("定时同步任务已启动，间隔 %s 分钟", interval)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def run_all(self) -> None:
        db = SessionLocal()
        try:
            results = SyncService(db).sync_all_enabled()
            failed = [r.source_name for r in results if r.status == "failed"]
            if failed:
                logger.warning("本次定时同步失败来源：%s", ", ".join(failed))
        finally:
            db.close()
