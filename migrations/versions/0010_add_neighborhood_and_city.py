"""add_neighborhood_and_city
Revision ID: 0010
Revises: 0009
"""
from typing import Optional, Sequence
from alembic import op
import sqlalchemy as sa

revision: str = '0010'
down_revision: Optional[str] = '0009'
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    # Rename existing city (neighbourhood) column to neighborhood
    op.alter_column('listings', 'city', new_column_name='neighborhood')
    # Add new city column for the municipality (e.g. Porto)
    op.add_column('listings', sa.Column('city', sa.Text(), nullable=True))
    op.execute("UPDATE listings SET city = 'Porto'")


def downgrade() -> None:
    op.drop_column('listings', 'city')
    op.alter_column('listings', 'neighborhood', new_column_name='city')
