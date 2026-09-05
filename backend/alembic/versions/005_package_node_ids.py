"""为套餐规则增加具体节点 ID 选择字段。

Revision ID: 005_package_node_ids
Revises: 004_subscription_name
Create Date: 2026-09-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_package_node_ids"
down_revision: Union[str, None] = "004_subscription_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("package_rules", sa.Column("node_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("package_rules", "node_ids")
