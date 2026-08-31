"""add optional secret for signed Feishu notification bots

Revision ID: c7e8f9a0b1c2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7e8f9a0b1c2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notify_channels",
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notify_channels", "secret_encrypted")
