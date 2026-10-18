"""记录 3x-ui 转发任务进度和执行阶段。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "027_forward_task_progress"
down_revision: Union[str, None] = "026_forward_modes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为已有和新建转发任务增加可持久化的进度信息。"""

    with op.batch_alter_table("forward_tasks") as batch:
        batch.add_column(
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "stage",
                sa.String(length=64),
                nullable=False,
                server_default="等待后台处理",
            )
        )


def downgrade() -> None:
    """删除转发任务进度字段。"""

    with op.batch_alter_table("forward_tasks") as batch:
        batch.drop_column("stage")
        batch.drop_column("progress")
