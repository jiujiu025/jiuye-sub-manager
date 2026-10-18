"""增加节点分类、3x-ui 服务器和异步转发映射。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "024_three_xui_forwarding"
down_revision: Union[str, None] = "023_node_health_breakdown"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增 3x-ui 业务表并为历史节点写入兼容分类。"""

    op.add_column(
        "nodes",
        sa.Column("node_category", sa.String(length=16), nullable=False, server_default="external"),
    )
    op.execute(
        sa.text(
            "UPDATE nodes SET node_category = CASE "
            "WHEN source_id IS NOT NULL OR source_type = 'upstream' THEN 'subscription' "
            "WHEN source_type = 'forwarded' THEN 'forwarded' "
            "ELSE 'external' END"
        )
    )
    op.create_index("ix_nodes_node_category", "nodes", ["node_category"])

    op.create_table(
        "three_xui_servers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("ip", sa.String(length=128), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("api_url", sa.String(length=512), nullable=False),
        sa.Column("api_token_encrypted", sa.Text(), nullable=False),
        sa.Column("api_token_prefix", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="3.8.5"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_api_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_api_status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_three_xui_servers_name"),
    )
    op.create_index("ix_three_xui_servers_name", "three_xui_servers", ["name"])
    op.create_index("ix_three_xui_servers_enabled", "three_xui_servers", ["enabled"])

    op.create_table(
        "forward_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_node_id", sa.Integer(), nullable=False),
        sa.Column("target_server_id", sa.Integer(), nullable=False),
        sa.Column("template", sa.String(length=32), nullable=False),
        sa.Column("listen_port", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_node_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_node_id"], ["nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_server_id"], ["three_xui_servers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["result_node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_forward_tasks_source_node_id", "forward_tasks", ["source_node_id"])
    op.create_index("ix_forward_tasks_target_server_id", "forward_tasks", ["target_server_id"])
    op.create_index("ix_forward_tasks_status", "forward_tasks", ["status"])

    op.create_table(
        "forwarded_node_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_node_id", sa.Integer(), nullable=False),
        sa.Column("forwarded_node_id", sa.Integer(), nullable=False),
        sa.Column("target_server_id", sa.Integer(), nullable=False),
        sa.Column("inbound_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("inbound_remark", sa.String(length=255), nullable=False),
        sa.Column("template", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_node_id"], ["nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["forwarded_node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_server_id"], ["three_xui_servers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("forwarded_node_id", name="uq_forwarded_mapping_forwarded_node"),
        sa.UniqueConstraint(
            "source_node_id", "target_server_id", "template",
            name="uq_forwarded_mapping_source_target_template",
        ),
    )
    op.create_index("ix_forwarded_node_mappings_source_node_id", "forwarded_node_mappings", ["source_node_id"])
    op.create_index("ix_forwarded_node_mappings_target_server_id", "forwarded_node_mappings", ["target_server_id"])
    op.create_index("ix_forwarded_node_mappings_status", "forwarded_node_mappings", ["status"])


def downgrade() -> None:
    """删除 3x-ui 转发表和节点分类字段。"""

    op.drop_index("ix_forwarded_node_mappings_status", table_name="forwarded_node_mappings")
    op.drop_index("ix_forwarded_node_mappings_target_server_id", table_name="forwarded_node_mappings")
    op.drop_index("ix_forwarded_node_mappings_source_node_id", table_name="forwarded_node_mappings")
    op.drop_table("forwarded_node_mappings")
    op.drop_index("ix_forward_tasks_status", table_name="forward_tasks")
    op.drop_index("ix_forward_tasks_target_server_id", table_name="forward_tasks")
    op.drop_index("ix_forward_tasks_source_node_id", table_name="forward_tasks")
    op.drop_table("forward_tasks")
    op.drop_index("ix_three_xui_servers_enabled", table_name="three_xui_servers")
    op.drop_index("ix_three_xui_servers_name", table_name="three_xui_servers")
    op.drop_table("three_xui_servers")
    op.drop_index("ix_nodes_node_category", table_name="nodes")
    op.drop_column("nodes", "node_category")
