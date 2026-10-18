"""为客户档案绑定可选的普通用户账号。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019_customer_account"
down_revision: Union[str, None] = "018_node_health"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为客户档案增加可选的一对一登录账号绑定。"""

    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("account_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_customers_account_user_id", ["account_user_id"], unique=True)
        batch_op.create_foreign_key(
            "fk_customers_account_user_id_users",
            "users",
            ["account_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """删除客户登录账号绑定字段。"""

    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_constraint("fk_customers_account_user_id_users", type_="foreignkey")
        batch_op.drop_index("ix_customers_account_user_id")
        batch_op.drop_column("account_user_id")
