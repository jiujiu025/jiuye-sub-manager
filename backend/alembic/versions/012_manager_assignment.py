"""add manager assignment to customers and subscriptions

Revision ID: 012_manager_assignment
Revises: 011_customer_subscriptions
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012_manager_assignment"
down_revision: Union[str, None] = "011_customer_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("manager_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_customers_manager_user_id", ["manager_user_id"])
        batch_op.create_foreign_key(
            "fk_customers_manager_user_id_users",
            "users",
            ["manager_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("customer_subscriptions") as batch_op:
        batch_op.add_column(
            sa.Column("manager_user_id", sa.Integer(), nullable=True),
        )
        batch_op.create_index(
            "ix_customer_subscriptions_manager_user_id",
            ["manager_user_id"],
        )
        batch_op.create_foreign_key(
            "fk_customer_subscriptions_manager_user_id_users",
            "users",
            ["manager_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("customer_subscriptions") as batch_op:
        batch_op.drop_constraint(
            "fk_customer_subscriptions_manager_user_id_users", type_="foreignkey"
        )
        batch_op.drop_index("ix_customer_subscriptions_manager_user_id")
        batch_op.drop_column("manager_user_id")
    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_constraint(
            "fk_customers_manager_user_id_users", type_="foreignkey"
        )
        batch_op.drop_index("ix_customers_manager_user_id")
        batch_op.drop_column("manager_user_id")
