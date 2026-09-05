"""为套餐增加订阅显示名称字段。

Revision ID: 004_subscription_name
Revises: 003_node_import_fields
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_subscription_name"
down_revision: Union[str, None] = "003_node_import_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "packages", sa.Column("subscription_name", sa.String(length=128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("packages", "subscription_name")
