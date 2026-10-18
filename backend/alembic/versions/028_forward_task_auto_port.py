"""记录转发任务是否使用自动端口。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "028_forward_task_auto_port"
down_revision: Union[str, None] = "027_forward_task_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为自动端口任务增加远端端口冲突处理所需的标记。"""

    with op.batch_alter_table("forward_tasks") as batch:
        batch.add_column(
            sa.Column("auto_port", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """删除自动端口标记。"""

    with op.batch_alter_table("forward_tasks") as batch:
        batch.drop_column("auto_port")
