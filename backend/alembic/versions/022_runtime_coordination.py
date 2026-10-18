"""增加多进程限流、缓存版本和定时任务租约表。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "022_runtime_coordination"
down_revision: Union[str, None] = "021_subscription_token_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建运行时协调表，不触碰业务表和生产数据内容。"""

    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rate_key", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_rate_limit_events_key_time",
        "rate_limit_events",
        ["rate_key", "occurred_at"],
    )
    op.create_table(
        "cache_namespace_versions",
        sa.Column("namespace", sa.String(length=255), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "scheduler_leases",
        sa.Column("job_name", sa.String(length=64), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("lease_until", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    """删除运行时协调表。"""

    op.drop_table("scheduler_leases")
    op.drop_table("cache_namespace_versions")
    op.drop_index("ix_rate_limit_events_key_time", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")
