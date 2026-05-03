"""add_lifetime_rent

Revision ID: 0002
Revises: 0001
"""
from typing import Optional, Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: Optional[str] = '0001'
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.add_column('listings', sa.Column('lifetime_rent', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('listings', 'lifetime_rent')
