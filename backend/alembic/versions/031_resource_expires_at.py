"""为资源节点和上游订阅源增加资源到期时间。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "031_resource_expires_at"
down_revision: Union[str, None] = "030_customer_subscription_lines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加资源到期字段；历史资源为空表示长期有效。"""

    op.add_column("nodes", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_nodes_expires_at", "nodes", ["expires_at"])
    op.add_column("sources", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_sources_expires_at", "sources", ["expires_at"])


def downgrade() -> None:
    """删除资源到期字段。"""

    op.drop_index("ix_sources_expires_at", table_name="sources")
    op.drop_column("sources", "expires_at")
    op.drop_index("ix_nodes_expires_at", table_name="nodes")
    op.drop_column("nodes", "expires_at")
