"""为站内通知增加外部渠道投递状态。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "020_notification_delivery"
down_revision: Union[str, None] = "019_customer_account"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为已有通知标记为 skipped，避免首次配置时补发历史消息。"""

    op.add_column(
        "notifications",
        sa.Column("telegram_push_status", sa.String(length=16), nullable=False, server_default="skipped"),
    )
    op.add_column("notifications", sa.Column("telegram_push_error", sa.Text(), nullable=True))
    op.add_column("notifications", sa.Column("telegram_pushed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "notifications",
        sa.Column("wechat_push_status", sa.String(length=16), nullable=False, server_default="skipped"),
    )
    op.add_column("notifications", sa.Column("wechat_push_error", sa.Text(), nullable=True))
    op.add_column("notifications", sa.Column("wechat_pushed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "notifications",
        sa.Column("external_push_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "notifications",
        sa.Column("external_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notifications_telegram_push_status",
        "notifications",
        ["telegram_push_status"],
    )
    op.create_index(
        "ix_notifications_wechat_push_status",
        "notifications",
        ["wechat_push_status"],
    )


def downgrade() -> None:
    """删除通知外部投递状态。"""

    op.drop_index("ix_notifications_wechat_push_status", table_name="notifications")
    op.drop_index("ix_notifications_telegram_push_status", table_name="notifications")
    op.drop_column("notifications", "external_last_attempt_at")
    op.drop_column("notifications", "external_push_attempts")
    op.drop_column("notifications", "wechat_pushed_at")
    op.drop_column("notifications", "wechat_push_error")
    op.drop_column("notifications", "wechat_push_status")
    op.drop_column("notifications", "telegram_pushed_at")
    op.drop_column("notifications", "telegram_push_error")
    op.drop_column("notifications", "telegram_push_status")
