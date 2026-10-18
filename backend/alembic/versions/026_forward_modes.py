"""增加 3x-ui 端口转发和入站出站两种模式。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "026_forward_modes"
down_revision: Union[str, None] = "025_notification_recipient_delivery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为历史任务保留入站出站语义，并增加可选入站备注。"""

    with op.batch_alter_table("forward_tasks") as batch:
        batch.add_column(
            sa.Column("forward_mode", sa.String(length=24), nullable=False, server_default="inbound_outbound")
        )
        batch.add_column(sa.Column("inbound_remark", sa.String(length=255), nullable=True))

    with op.batch_alter_table("forwarded_node_mappings") as batch:
        batch.add_column(
            sa.Column("forward_mode", sa.String(length=24), nullable=False, server_default="inbound_outbound")
        )
        batch.drop_constraint("uq_forwarded_mapping_source_target_template", type_="unique")
        batch.create_unique_constraint(
            "uq_forwarded_mapping_source_target_template",
            ["source_node_id", "target_server_id", "template", "forward_mode"],
        )


def downgrade() -> None:
    """回退转发模式字段和复合唯一约束。"""

    with op.batch_alter_table("forwarded_node_mappings") as batch:
        batch.drop_constraint("uq_forwarded_mapping_source_target_template", type_="unique")
        batch.drop_column("forward_mode")
        batch.create_unique_constraint(
            "uq_forwarded_mapping_source_target_template",
            ["source_node_id", "target_server_id", "template"],
        )
    with op.batch_alter_table("forward_tasks") as batch:
        batch.drop_column("inbound_remark")
        batch.drop_column("forward_mode")
