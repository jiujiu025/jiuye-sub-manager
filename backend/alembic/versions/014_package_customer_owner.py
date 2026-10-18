"""add business customer ownership to packages"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014_package_customer_owner"
down_revision: Union[str, None] = "013_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    with op.batch_alter_table("packages") as batch_op:
        batch_op.add_column(sa.Column("owner_customer_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_packages_owner_customer_id", ["owner_customer_id"])
        batch_op.create_foreign_key(
            "fk_packages_owner_customer_id_customers",
            "customers",
            ["owner_customer_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("packages") as batch_op:
        batch_op.drop_constraint(
            "fk_packages_owner_customer_id_customers", type_="foreignkey"
        )
        batch_op.drop_index("ix_packages_owner_customer_id")
        batch_op.drop_column("owner_customer_id")
