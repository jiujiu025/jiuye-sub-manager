"""定时同步任务调度。"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import SessionLocal
from app.services.settings_service import SettingsService
from app.services.sync_service import SyncService
from app.services.notification_service import NotificationService
from app.services.notification_delivery_service import NotificationDeliveryService
from app.services.node_health_service import NodeHealthService
from app.services.three_xui_service import ThreeXUIService
from app.services.geoip_service import GeoIPService
from app.core.config import get_settings
from app.models.base import utcnow
from app.core.coordination import SchedulerLeaseStore

logger = logging.getLogger(__name__)


class SyncScheduler:
    """基于 APScheduler 的进程内定时同步。"""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self.lease_store = SchedulerLeaseStore()

    def start(self) -> None:
        db = SessionLocal()
        try:
            runtime = SettingsService(db).get()
        finally:
            db.close()
        self.apply_runtime_settings(
            runtime.sync_enabled,
            runtime.sync_interval_minutes,
            runtime.health_enabled,
            runtime.health_interval_minutes,
        )
        if not self.scheduler.running:
            self.scheduler.start()
        if runtime.sync_enabled and runtime.sync_interval_minutes > 0:
            logger.info(
                "定时同步任务已启动，间隔 %s 分钟", runtime.sync_interval_minutes
            )
        else:
            logger.info("定时同步已禁用")

    def apply_runtime_settings(
        self,
        sync_enabled: bool,
        interval_minutes: int,
        health_enabled: bool = True,
        health_interval_minutes: int = 5,
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
        health_job = self.scheduler.get_job("check_node_health")
        if health_enabled and health_interval_minutes > 0:
            if health_job is not None:
                health_job.modify(
                    trigger=IntervalTrigger(minutes=health_interval_minutes)
                )
            else:
                self.scheduler.add_job(
                    self.run_health_checks,
                    trigger=IntervalTrigger(minutes=health_interval_minutes),
                    id="check_node_health",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
        elif health_job is not None:
            health_job.remove()
        notification_job = self.scheduler.get_job("generate_notifications")
        if notification_job is None:
            self.scheduler.add_job(
                self.run_notifications,
                trigger=IntervalTrigger(minutes=1),
                id="generate_notifications",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        forwarding_job = self.scheduler.get_job("process_three_xui_forward_tasks")
        if forwarding_job is None:
            self.scheduler.add_job(
                self.run_three_xui_forward_tasks,
                trigger=IntervalTrigger(seconds=30),
                id="process_three_xui_forward_tasks",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        geoip_job = self.scheduler.get_job("resolve_node_countries")
        if get_settings().geoip_enabled and get_settings().geoip_interval_minutes > 0:
            if geoip_job is not None:
                geoip_job.modify(
                    trigger=IntervalTrigger(minutes=get_settings().geoip_interval_minutes)
                )
            else:
                self.scheduler.add_job(
                    self.run_country_resolution,
                    trigger=IntervalTrigger(minutes=get_settings().geoip_interval_minutes),
                    id="resolve_node_countries",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    next_run_time=utcnow(),
                )
        elif geoip_job is not None:
            geoip_job.remove()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def run_all(self) -> None:
        if not self.lease_store.try_acquire("sync_all_sources", 1800):
            logger.info("跳过重复同步任务：其他 worker 正在执行")
            return
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
            self.lease_store.release("sync_all_sources")

    def run_notifications(self) -> None:
        """定时生成到期提醒并归档过期通知。"""

        if not self.lease_store.try_acquire("generate_notifications", 300):
            logger.info("跳过重复通知任务：其他 worker 正在执行")
            return
        db = SessionLocal()
        try:
            service = NotificationService(db)
            service.ensure_expiry_notifications()
            service.archive_stale()
            NotificationDeliveryService(db).dispatch_pending()
        except Exception:
            logger.exception("定时通知生成或外部投递失败")
        finally:
            db.close()
            self.lease_store.release("generate_notifications")

    def run_health_checks(self) -> None:
        """检测所有启用节点并生成状态变更通知。"""

        if not self.lease_store.try_acquire("check_node_health", 1800):
            logger.info("跳过重复健康检查：其他 worker 正在执行")
            return
        db = SessionLocal()
        try:
            # 定时任务检测资源池中的全部启用节点，包含上游订阅节点和已转发节点。
            NodeHealthService(db).run_all(include_all=True)
        except Exception:
            logger.exception("定时节点健康检测失败")
        finally:
            db.close()
            self.lease_store.release("check_node_health")

    def run_three_xui_forward_tasks(self) -> None:
        """每 30 秒处理待转发任务，避免 HTTP 请求长时间等待面板。"""

        if not self.lease_store.try_acquire("process_three_xui_forward_tasks", 1200):
            logger.info("跳过重复 3x-ui 转发任务：其他 worker 正在执行")
            return
        db = SessionLocal()
        try:
            processed = ThreeXUIService(db).process_pending()
            if processed:
                logger.info("本次处理 3x-ui 转发任务 %s 个", processed)
        except Exception:
            logger.exception("3x-ui 转发任务处理失败")
        finally:
            db.close()
            self.lease_store.release("process_three_xui_forward_tasks")

    def run_country_resolution(self) -> None:
        """后台补全缺失地区，不让第三方接口影响同步任务。"""

        if not self.lease_store.try_acquire("resolve_node_countries", 900):
            logger.info("跳过重复地区识别任务：其他 worker 正在执行")
            return
        db = SessionLocal()
        service = GeoIPService(db)
        try:
            result = service.resolve_nodes(limit=get_settings().geoip_batch_size)
            if result["resolved"] or result["failed"]:
                logger.info(
                    "地区识别完成：处理 %s，识别 %s，失败 %s",
                    result["processed"],
                    result["resolved"],
                    result["failed"],
                )
        except Exception:
            db.rollback()
            logger.exception("后台地区识别任务失败")
        finally:
            service.close()
            db.close()
            self.lease_store.release("resolve_node_countries")


scheduler = SyncScheduler()
