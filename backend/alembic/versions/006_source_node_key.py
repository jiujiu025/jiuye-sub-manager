"""为上游节点增加来源内稳定标识。

Revision ID: 006_source_node_key
Revises: 005_package_node_ids
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_source_node_key"
down_revision: Union[str, None] = "005_package_node_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("source_node_key", sa.String(length=64), nullable=True))
    op.create_index("ix_nodes_source_node_key", "nodes", ["source_node_key"])


def downgrade() -> None:
    op.drop_index("ix_nodes_source_node_key", table_name="nodes")
    op.drop_column("nodes", "source_node_key")
