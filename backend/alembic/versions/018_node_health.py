"""add node health monitoring fields

Revision ID: 018_node_health
Revises: 017_subscription_cost_split
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "018_node_health"
down_revision: Union[str, None] = "017_subscription_cost_split"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加节点健康状态和连续检测计数。"""

    op.add_column(
        "nodes",
        sa.Column("health_status", sa.String(length=16), nullable=False, server_default="unknown"),
    )
    op.add_column("nodes", sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("nodes", sa.Column("health_latency_ms", sa.Integer(), nullable=True))
    op.add_column("nodes", sa.Column("health_detail", sa.Text(), nullable=True))
    op.add_column(
        "nodes",
        sa.Column("health_failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "nodes",
        sa.Column("health_success_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "nodes",
        sa.Column("health_incident_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_nodes_health_status", "nodes", ["health_status"])


def downgrade() -> None:
    """删除节点健康状态字段。"""

    op.drop_index("ix_nodes_health_status", table_name="nodes")
    op.drop_column("nodes", "health_incident_started_at")
    op.drop_column("nodes", "health_success_count")
    op.drop_column("nodes", "health_failure_count")
    op.drop_column("nodes", "health_detail")
    op.drop_column("nodes", "health_latency_ms")
    op.drop_column("nodes", "health_checked_at")
    op.drop_column("nodes", "health_status")
