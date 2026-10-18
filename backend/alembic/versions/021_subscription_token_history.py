"""增加客户订阅 Token 策略和历史版本。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "021_subscription_token_history"
down_revision: Union[str, None] = "020_notification_delivery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为当前 Token 增加来源信息，并保存后续版本历史。"""

    with op.batch_alter_table("subscription_tokens") as batch_op:
        batch_op.add_column(
            sa.Column("token_mode", sa.String(length=16), nullable=False, server_default="generated")
        )
        batch_op.add_column(sa.Column("source_package_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_subscription_tokens_source_package_id", ["source_package_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_subscription_tokens_source_package_id_packages",
            "packages",
            ["source_package_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "subscription_token_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_mode", sa.String(length=16), nullable=False, server_default="generated"),
        sa.Column("source_package_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["customer_subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_package_id"], ["packages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_subscription_token_versions_subscription_id", "subscription_token_versions", ["subscription_id"])
    op.create_index("ix_subscription_token_versions_token_hash", "subscription_token_versions", ["token_hash"])
    op.create_index("ix_subscription_token_versions_source_package_id", "subscription_token_versions", ["source_package_id"])
    op.create_index("ix_subscription_token_versions_actor_user_id", "subscription_token_versions", ["actor_user_id"])
    op.execute(
        sa.text(
            """
            INSERT INTO subscription_token_versions (
                subscription_id, token_hash, token_prefix, token_encrypted,
                token_mode, source_package_id, version, action, actor_user_id,
                valid_from, valid_to, reason, created_at
            )
            SELECT subscription_id, token_hash, token_prefix, token_encrypted,
                   token_mode, source_package_id, 1, 'legacy', NULL,
                   created_at, revoked_at, '迁移前已有 Token', created_at
            FROM subscription_tokens
            """
        )
    )


def downgrade() -> None:
    """删除 Token 历史与来源字段。"""

    op.drop_index("ix_subscription_token_versions_actor_user_id", table_name="subscription_token_versions")
    op.drop_index("ix_subscription_token_versions_source_package_id", table_name="subscription_token_versions")
    op.drop_index("ix_subscription_token_versions_token_hash", table_name="subscription_token_versions")
    op.drop_index("ix_subscription_token_versions_subscription_id", table_name="subscription_token_versions")
    op.drop_table("subscription_token_versions")
    with op.batch_alter_table("subscription_tokens") as batch_op:
        batch_op.drop_constraint("fk_subscription_tokens_source_package_id_packages", type_="foreignkey")
        batch_op.drop_index("ix_subscription_tokens_source_package_id")
        batch_op.drop_column("source_package_id")
        batch_op.drop_column("token_mode")
