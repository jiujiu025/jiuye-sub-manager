"""为节点池增加来源类型、来源子类型与用户名字段。

Revision ID: 003_node_import_fields
Revises: 002_token_encrypted
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_node_import_fields"
down_revision: Union[str, None] = "002_token_encrypted"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("username", sa.Text(), nullable=True))
    op.add_column("nodes", sa.Column("source_type", sa.String(length=16), nullable=True))
    op.add_column("nodes", sa.Column("source_subtype", sa.String(length=32), nullable=True))
    op.create_index("ix_nodes_source_type", "nodes", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_nodes_source_type", table_name="nodes")
    op.drop_column("nodes", "source_subtype")
    op.drop_column("nodes", "source_type")
    op.drop_column("nodes", "username")
