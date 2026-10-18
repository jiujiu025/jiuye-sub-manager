"""add in-app notifications

Revision ID: 013_notifications
Revises: 012_manager_assignment
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013_notifications"
down_revision: Union[str, None] = "012_manager_assignment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["customer_subscriptions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("ix_notifications_subscription_id", "notifications", ["subscription_id"])
    op.create_index("ix_notifications_kind", "notifications", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_notifications_kind", table_name="notifications")
    op.drop_index("ix_notifications_subscription_id", table_name="notifications")
    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
    op.drop_table("notifications")
