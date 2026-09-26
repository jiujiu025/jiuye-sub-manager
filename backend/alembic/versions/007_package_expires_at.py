"""为套餐增加可选到期时间。

Revision ID: 007_package_expires_at
Revises: 006_source_node_key
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_package_expires_at"
down_revision: Union[str, None] = "006_source_node_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "packages",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_packages_expires_at", "packages", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_packages_expires_at", table_name="packages")
    op.drop_column("packages", "expires_at")
