"""memory_corrections 人类反馈数据池

V0.0.5 ⑤ 记忆审查与人类反馈闭环:用户对 AI 萃取的低置信度实体做
confirm / correct / delete 三类操作时,结构化记录前后快照与原因,
作为 V0.0.6 self-improvement loop 的训练信号。

Revision ID: b8d195cf3e7a
Revises: 7a3c4d5e6f01
Create Date: 2026-06-26 23:50:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8d195cf3e7a'
down_revision: Union[str, None] = '7a3c4d5e6f01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'memory_corrections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('entity_id', sa.String(length=128), nullable=False),
        sa.Column('action', sa.String(length=16), nullable=False),
        sa.Column('before', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('reason', sa.String(length=256), nullable=True),
        sa.Column('source_dialogue_id', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_memory_corrections_user_id'),
                    'memory_corrections', ['user_id'], unique=False)
    op.create_index(op.f('ix_memory_corrections_entity_id'),
                    'memory_corrections', ['entity_id'], unique=False)
    op.create_index(op.f('ix_memory_corrections_action'),
                    'memory_corrections', ['action'], unique=False)
    op.create_index(op.f('ix_memory_corrections_created_at'),
                    'memory_corrections', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_memory_corrections_created_at'),
                  table_name='memory_corrections')
    op.drop_index(op.f('ix_memory_corrections_action'),
                  table_name='memory_corrections')
    op.drop_index(op.f('ix_memory_corrections_entity_id'),
                  table_name='memory_corrections')
    op.drop_index(op.f('ix_memory_corrections_user_id'),
                  table_name='memory_corrections')
    op.drop_table('memory_corrections')
