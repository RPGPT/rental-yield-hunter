"""add_is_favorite
Revision ID: 0006
Revises: 0005
"""
from typing import Optional, Sequence
from alembic import op
import sqlalchemy as sa

revision: str = '0006'
down_revision: Optional[str] = '0005'
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    # Clean up any /hpr/ URLs that slipped through before the repository sanitizer was added
    op.execute("UPDATE listings SET url = regexp_replace(url, '/hpr/', '/', 'g') WHERE url LIKE '%/hpr/%'")
    # Add is_favorite column — default false for all existing and new rows
    op.add_column('listings', sa.Column('is_favorite', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('listings', 'is_favorite')

