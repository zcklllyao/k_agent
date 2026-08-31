"""知识库加 chat_enabled

Revision ID: f30e6fa335e9
Revises: 8440c3519b07
Create Date: 2026-06-12 16:22:02.408962

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f30e6fa335e9'
down_revision: Union[str, None] = '8440c3519b07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 存量知识库都是「默认库」，对话检索默认开启 → server_default true。
    # 加列后去掉 server_default，由 ORM 控制新建库的默认值（普通库默认关）。
    op.add_column(
        'knowledge_bases',
        sa.Column('chat_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column('knowledge_bases', 'chat_enabled', server_default=None)


def downgrade() -> None:
    op.drop_column('knowledge_bases', 'chat_enabled')
