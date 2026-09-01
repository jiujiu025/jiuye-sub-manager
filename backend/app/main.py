"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, dashboard, health, logs, nodes, packages, sources, subscribe
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db import engine
from app.seed import ensure_admin
from app.tasks.scheduler import SyncScheduler

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用启动时检查管理员账号；关闭时释放数据库连接池。"""

    ensure_admin()
    scheduler = SyncScheduler()
    if settings.sync_enabled:
        scheduler.start()
    yield
    scheduler.shutdown()
    engine.dispose()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
register_exception_handlers(app)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(admin.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(nodes.router, prefix="/api")
app.include_router(packages.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(subscribe.router)
