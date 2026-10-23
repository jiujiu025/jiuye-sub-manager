"""增加客户订阅线路明细和独立到期时间。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "030_customer_subscription_lines"
down_revision: Union[str, None] = "029_geoip_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建客户订阅线路快照表。"""

    op.create_table(
        "customer_subscription_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remark", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["customer_subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("subscription_id", "node_id", name="uq_customer_subscription_lines_node"),
    )
    op.create_index(
        "ix_customer_subscription_lines_subscription_id",
        "customer_subscription_lines",
        ["subscription_id"],
    )
    op.create_index(
        "ix_customer_subscription_lines_node_id",
        "customer_subscription_lines",
        ["node_id"],
    )
    op.create_index(
        "ix_customer_subscription_lines_expires_at",
        "customer_subscription_lines",
        ["expires_at"],
    )
    op.create_index(
        "ix_customer_subscription_lines_status",
        "customer_subscription_lines",
        ["status"],
    )


def downgrade() -> None:
    """删除客户订阅线路明细表。"""

    op.drop_index("ix_customer_subscription_lines_status", table_name="customer_subscription_lines")
    op.drop_index("ix_customer_subscription_lines_expires_at", table_name="customer_subscription_lines")
    op.drop_index("ix_customer_subscription_lines_node_id", table_name="customer_subscription_lines")
    op.drop_index("ix_customer_subscription_lines_subscription_id", table_name="customer_subscription_lines")
    op.drop_table("customer_subscription_lines")
