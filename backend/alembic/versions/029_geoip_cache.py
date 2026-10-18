"""增加公网 IP 地区识别缓存。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "029_geoip_cache"
down_revision: Union[str, None] = "028_forward_task_auto_port"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 IP 地理结果缓存表。"""

    op.create_table(
        "geoip_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("country_code", sa.String(length=8), nullable=True),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="success"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_geoip_cache_ip_address", "geoip_cache", ["ip_address"], unique=True)
    op.create_index("ix_geoip_cache_expires_at", "geoip_cache", ["expires_at"], unique=False)


def downgrade() -> None:
    """删除 IP 地理结果缓存表。"""

    op.drop_index("ix_geoip_cache_expires_at", table_name="geoip_cache")
    op.drop_index("ix_geoip_cache_ip_address", table_name="geoip_cache")
    op.drop_table("geoip_cache")
