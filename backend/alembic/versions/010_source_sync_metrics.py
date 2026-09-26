"""增加来源条件请求与同步健康指标。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010_source_sync_metrics"
down_revision: Union[str, None] = "009_subscription_token_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("etag", sa.String(length=255), nullable=True))
    op.add_column("sources", sa.Column("last_modified", sa.String(length=255), nullable=True))
    op.add_column("sources", sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_success_node_count", sa.Integer(), nullable=True))
    op.add_column("sources", sa.Column("last_sync_duration_ms", sa.Integer(), nullable=True))
    op.add_column(
        "sources",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    # SQLite 不支持直接执行 ALTER COLUMN；保留数据库默认值 0 与 ORM 语义一致。


def downgrade() -> None:
    op.drop_column("sources", "consecutive_failures")
    op.drop_column("sources", "last_sync_duration_ms")
    op.drop_column("sources", "last_success_node_count")
    op.drop_column("sources", "last_success_at")
    op.drop_column("sources", "last_modified")
    op.drop_column("sources", "etag")
