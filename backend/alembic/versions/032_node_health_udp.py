"""增加节点健康检查的 UDP 分项结果。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "032_node_health_udp"
down_revision: Union[str, None] = "031_resource_expires_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """保存 UDP 协议链路的检测状态和延迟。"""

    op.add_column(
        "nodes",
        sa.Column(
            "health_udp_status",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column("nodes", sa.Column("health_udp_latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    """删除节点健康检查的 UDP 分项结果。"""

    op.drop_column("nodes", "health_udp_latency_ms")
    op.drop_column("nodes", "health_udp_status")
