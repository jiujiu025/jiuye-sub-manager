"""add customer subscriptions and independent tokens

Revision ID: 011_customer_subscriptions
Revises: 010_source_sync_metrics
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011_customer_subscriptions"
down_revision: Union[str, None] = "010_source_sync_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("contact", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("first_purchase_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customers_name", "customers", ["name"])

    op.create_table(
        "customer_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sale_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["package_id"], ["packages.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_customer_subscriptions_customer_id", "customer_subscriptions", ["customer_id"])
    op.create_index("ix_customer_subscriptions_package_id", "customer_subscriptions", ["package_id"])
    op.create_index("ix_customer_subscriptions_status", "customer_subscriptions", ["status"])
    op.create_index("ix_customer_subscriptions_expires_at", "customer_subscriptions", ["expires_at"])

    op.create_table(
        "subscription_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_access_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_access_ip", sa.String(length=64), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["subscription_id"], ["customer_subscriptions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("subscription_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_subscription_tokens_subscription_id", "subscription_tokens", ["subscription_id"])
    op.create_index("ix_subscription_tokens_token_hash", "subscription_tokens", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_subscription_tokens_token_hash", table_name="subscription_tokens")
    op.drop_index("ix_subscription_tokens_subscription_id", table_name="subscription_tokens")
    op.drop_table("subscription_tokens")
    op.drop_index("ix_customer_subscriptions_expires_at", table_name="customer_subscriptions")
    op.drop_index("ix_customer_subscriptions_status", table_name="customer_subscriptions")
    op.drop_index("ix_customer_subscriptions_package_id", table_name="customer_subscriptions")
    op.drop_index("ix_customer_subscriptions_customer_id", table_name="customer_subscriptions")
    op.drop_table("customer_subscriptions")
    op.drop_index("ix_customers_name", table_name="customers")
    op.drop_table("customers")
