"""add_active_inactive_since

Revision ID: 0003
Revises: 0002
"""
from typing import Optional, Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Optional[str] = '0002'
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('listings', sa.Column('active', sa.Boolean(), server_default='true', nullable=True))
    op.add_column('listings', sa.Column('inactive_since', sa.TIMESTAMP(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('listings', 'inactive_since')
    op.drop_column('listings', 'active')
