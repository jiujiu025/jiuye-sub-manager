"""split company and sales cost prices for customer subscriptions

Revision ID: 017_subscription_cost_split
Revises: 016_node_operations
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017_subscription_cost_split"
down_revision: Union[str, None] = "016_node_operations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customer_subscriptions",
        sa.Column("company_cost_price", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "customer_subscriptions",
        sa.Column("sales_cost_price", sa.Numeric(12, 2), nullable=True),
    )
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE customer_subscriptions "
            "SET company_cost_price = cost_price "
            "WHERE cost_price IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("customer_subscriptions", "sales_cost_price")
    op.drop_column("customer_subscriptions", "company_cost_price")
