"""add knowledge base markdown overview

Revision ID: a1b2c3d4e5f6
Revises: 6727223d45f9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "6727223d45f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_bases", sa.Column("overview_file_key", sa.String(length=512), nullable=True))
    op.add_column(
        "knowledge_bases",
        sa.Column("overview_status", sa.String(length=16), nullable=False, server_default="empty"),
    )
    op.add_column("knowledge_bases", sa.Column("overview_error", sa.Text(), nullable=True))
    op.add_column("knowledge_bases", sa.Column("overview_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("knowledge_bases", "overview_status", server_default=None)


def downgrade() -> None:
    op.drop_column("knowledge_bases", "overview_updated_at")
    op.drop_column("knowledge_bases", "overview_error")
    op.drop_column("knowledge_bases", "overview_status")
    op.drop_column("knowledge_bases", "overview_file_key")
