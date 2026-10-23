"""导入所有 ORM 模型，供 Alembic 自动生成迁移使用。"""

from app.models.log import AdminLog, SubscriptionLog, SyncLog
from app.models.notification import Notification
from app.models.node import Node, NodeCodeSequence
from app.models.package import Package, PackageRule
from app.models.customer import Customer
from app.models.subscription import (
    CustomerSubscription,
    CustomerSubscriptionLine,
    SubscriptionToken,
    SubscriptionTokenVersion,
)
from app.models.runtime import CacheNamespaceVersion, RateLimitEvent, SchedulerLease
from app.models.three_xui import ForwardTask, ForwardedNodeMapping, ThreeXUIServer
from app.models.geo import GeoIPCache
from app.models.health import NodeHealthSample, NodeIncident
from app.models.setting import SystemSetting
from app.models.source import Source
from app.models.user import User

__all__ = [
    "AdminLog",
    "Customer",
    "CustomerSubscription",
    "CustomerSubscriptionLine",
    "Node",
    "NodeCodeSequence",
    "Notification",
    "Package",
    "PackageRule",
    "Source",
    "SubscriptionLog",
    "SyncLog",
    "SystemSetting",
    "SubscriptionToken",
    "SubscriptionTokenVersion",
    "User",
    "CacheNamespaceVersion",
    "RateLimitEvent",
    "SchedulerLease",
    "ForwardTask",
    "ForwardedNodeMapping",
    "ThreeXUIServer",
    "GeoIPCache",
    "NodeHealthSample",
    "NodeIncident",
]
