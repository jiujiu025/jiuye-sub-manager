"""为套餐增加 Token 加密字段，用于后台展示订阅地址。

Revision ID: 002_token_encrypted
Revises: 56858ed87d50
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_token_encrypted"
down_revision: Union[str, None] = "56858ed87d50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("packages", sa.Column("token_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("packages", "token_encrypted")
