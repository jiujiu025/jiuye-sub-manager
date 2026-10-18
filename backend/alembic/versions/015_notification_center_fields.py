"""add notification center metadata and archive fields"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015_notification_center_fields"
down_revision: Union[str, None] = "014_package_customer_owner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(
            sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal")
        )
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("target_type", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("target_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_notifications_priority", ["priority"])
        batch_op.create_index("ix_notifications_archived_at", ["archived_at"])


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_index("ix_notifications_archived_at")
        batch_op.drop_index("ix_notifications_priority")
        batch_op.drop_column("target_id")
        batch_op.drop_column("target_type")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("priority")
