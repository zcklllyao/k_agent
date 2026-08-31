"""loop_runs + loop_iterations Verifier Loop 状态外置表

Revision ID: 7a3c4d5e6f01
Revises: bf7ad4190462
Create Date: 2026-06-26 21:00:00.000000

V0.0.5 ② Loop Engineering 落地的状态外置层:
- loop_runs: 一次完整 Loop(对应一份研究报告或一次定时任务结果)
- loop_iterations: Loop 内每一轮 generate→verify→decide 的详细记录
状态外置 = 进程崩了/worker 重启也能从 checkpoint 恢复;每轮回炉决策完整 audit trail。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7a3c4d5e6f01'
down_revision: Union[str, None] = 'bf7ad4190462'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # loop_runs:一次完整 Verifier Loop
    op.create_table(
        'loop_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('task_type', sa.String(length=32), nullable=False),
        sa.Column('task_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='running'),
        sa.Column('iterations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('final_score', sa.Float(), nullable=True),
        sa.Column('pass_threshold', sa.Float(), nullable=False, server_default='0.7'),
        sa.Column('max_iterations', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('generator_model', sa.String(length=128), nullable=True),
        sa.Column('verifier_model', sa.String(length=128), nullable=True),
        sa.Column('verifier_kind', sa.String(length=16), nullable=True),
        sa.Column('rubric_name', sa.String(length=32), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_loop_runs_user_id'), 'loop_runs', ['user_id'], unique=False)
    op.create_index(op.f('ix_loop_runs_task_type'), 'loop_runs', ['task_type'], unique=False)
    op.create_index(op.f('ix_loop_runs_task_id'), 'loop_runs', ['task_id'], unique=False)
    op.create_index(op.f('ix_loop_runs_status'), 'loop_runs', ['status'], unique=False)

    # loop_iterations:每轮迭代记录
    op.create_table(
        'loop_iterations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('iteration_no', sa.Integer(), nullable=False),
        sa.Column('artifact_snapshot', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='{}'),
        sa.Column('scores', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='{}'),
        sa.Column('feedback', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='{}'),
        sa.Column('decision', sa.String(length=16), nullable=False),
        sa.Column('repair_action', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['loop_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_loop_iterations_run_id'), 'loop_iterations', ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_loop_iterations_run_id'), table_name='loop_iterations')
    op.drop_table('loop_iterations')
    op.drop_index(op.f('ix_loop_runs_status'), table_name='loop_runs')
    op.drop_index(op.f('ix_loop_runs_task_id'), table_name='loop_runs')
    op.drop_index(op.f('ix_loop_runs_task_type'), table_name='loop_runs')
    op.drop_index(op.f('ix_loop_runs_user_id'), table_name='loop_runs')
    op.drop_table('loop_runs')
