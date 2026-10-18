"""保存节点健康检查的 TCP/TLS 分项结果。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "023_node_health_breakdown"
down_revision: Union[str, None] = "022_runtime_coordination"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加可直接展示的分项探测状态和延迟。"""

    op.add_column(
        "nodes",
        sa.Column("health_tcp_status", sa.String(length=16), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "nodes",
        sa.Column("health_tls_status", sa.String(length=16), nullable=False, server_default="unknown"),
    )
    op.add_column("nodes", sa.Column("health_tcp_latency_ms", sa.Integer(), nullable=True))
    op.add_column("nodes", sa.Column("health_tls_latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    """删除健康检查分项字段。"""

    op.drop_column("nodes", "health_tls_latency_ms")
    op.drop_column("nodes", "health_tcp_latency_ms")
    op.drop_column("nodes", "health_tls_status")
    op.drop_column("nodes", "health_tcp_status")
