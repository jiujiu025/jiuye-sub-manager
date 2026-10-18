"""add node operation metadata and monotonic node codes

Revision ID: 016_node_operations
Revises: 015_notification_center_fields
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016_node_operations"
down_revision: Union[str, None] = "015_notification_center_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "node_code_sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False),
    )
    op.add_column("nodes", sa.Column("node_code", sa.String(length=32), nullable=True))
    op.add_column("nodes", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("nodes", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    node_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM nodes ORDER BY id"))]
    for node_id in node_ids:
        bind.execute(
            sa.text(
                "UPDATE nodes SET node_code = :node_code, last_seen_at = "
                "COALESCE(last_seen_at, created_at) WHERE id = :node_id"
            ),
            {"node_code": f"N-{node_id:06d}", "node_id": node_id},
        )
    next_value = (max(node_ids) + 1) if node_ids else 1
    bind.execute(
        sa.text("INSERT INTO node_code_sequences (id, next_value) VALUES (1, :next_value)"),
        {"next_value": next_value},
    )
    op.create_index("ix_nodes_node_code", "nodes", ["node_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_nodes_node_code", table_name="nodes")
    op.drop_column("nodes", "last_seen_at")
    op.drop_column("nodes", "note")
    op.drop_column("nodes", "node_code")
    op.drop_table("node_code_sequences")
