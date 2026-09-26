"""增加订阅 Token 审计字段。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_subscription_token_audit"
down_revision: Union[str, None] = "008_package_owner_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("packages", sa.Column("token_name", sa.String(length=128), nullable=True))
    op.add_column("packages", sa.Column("token_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("packages", sa.Column("token_last_access_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("packages", sa.Column("token_last_access_ip", sa.String(length=64), nullable=True))
    op.add_column(
        "packages",
        sa.Column("token_access_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("packages", sa.Column("token_revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE packages SET token_name = name WHERE token_name IS NULL"))
    op.execute(sa.text("UPDATE packages SET token_created_at = created_at WHERE token_created_at IS NULL"))
    # SQLite 不支持直接执行 ALTER COLUMN；保留数据库默认值 0 与 ORM 语义一致。


def downgrade() -> None:
    op.drop_column("packages", "token_revoked_at")
    op.drop_column("packages", "token_access_count")
    op.drop_column("packages", "token_last_access_ip")
    op.drop_column("packages", "token_last_access_at")
    op.drop_column("packages", "token_created_at")
    op.drop_column("packages", "token_name")
