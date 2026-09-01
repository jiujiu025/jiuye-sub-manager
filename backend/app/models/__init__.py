"""导入所有 ORM 模型，供 Alembic 自动生成迁移使用。"""

from app.models.log import AdminLog, SubscriptionLog, SyncLog
from app.models.node import Node
from app.models.package import Package, PackageRule
from app.models.setting import SystemSetting
from app.models.source import Source
from app.models.user import User

__all__ = [
    "AdminLog",
    "Node",
    "Package",
    "PackageRule",
    "Source",
    "SubscriptionLog",
    "SyncLog",
    "SystemSetting",
    "User",
]
