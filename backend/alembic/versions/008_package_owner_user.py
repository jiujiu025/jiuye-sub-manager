"""为套餐增加普通用户归属字段。

Revision ID: 008_package_owner_user
Revises: 007_package_expires_at
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_package_owner_user"
down_revision: Union[str, None] = "007_package_expires_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为历史套餐保留 NULL，新增套餐按需绑定普通用户。"""

    # SQLite 不支持直接通过 ALTER TABLE 增加约束，使用 batch 模式兼容重建表。
    with op.batch_alter_table("packages", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "owner_user_id",
                sa.Integer(),
                sa.ForeignKey(
                    "users.id",
                    name="fk_packages_owner_user_id_users",
                    ondelete="SET NULL",
                ),
                nullable=True,
            )
        )
    op.create_index("ix_packages_owner_user_id", "packages", ["owner_user_id"])


def downgrade() -> None:
    """移除套餐用户归属字段。"""

    op.drop_index("ix_packages_owner_user_id", table_name="packages")
    with op.batch_alter_table("packages", schema=None) as batch_op:
        batch_op.drop_column("owner_user_id")
