"""记录通知已成功投递的具体接收人，避免部分成功时重复发送。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "025_notification_recipient_delivery"
down_revision: Union[str, None] = "024_three_xui_forwarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加 Telegram 与微信公众号的已投递接收人记录。"""

    op.add_column(
        "notifications",
        sa.Column("telegram_delivered_chat_ids", sa.JSON(), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("wechat_delivered_openids", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """删除按接收人记录的外部投递状态。"""

    op.drop_column("notifications", "wechat_delivered_openids")
    op.drop_column("notifications", "telegram_delivered_chat_ids")
