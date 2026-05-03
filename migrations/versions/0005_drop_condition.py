"""drop_condition
Revision ID: 0005
Revises: 0004
"""
from typing import Optional, Sequence
from alembic import op
import sqlalchemy as sa

revision: str = '0005'
down_revision: Optional[str] = '0004'
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.drop_column('listings', 'condition')


def downgrade() -> None:
    op.add_column('listings', sa.Column('condition', sa.Text(), nullable=True))

