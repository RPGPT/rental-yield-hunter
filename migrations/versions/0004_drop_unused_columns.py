"""drop_unused_columns
Revision ID: 0004
Revises: 0003
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Optional[str] = "0003"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.drop_column("listings", "parish")
    op.drop_column("listings", "latitude")
    op.drop_column("listings", "longitude")
    op.drop_column("listings", "has_elevator")
    op.drop_column("listings", "rent_detected")


def downgrade() -> None:
    op.add_column("listings", sa.Column("rent_detected", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("has_elevator", sa.Boolean(), nullable=True))
    op.add_column("listings", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("listings", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("listings", sa.Column("parish", sa.Text(), nullable=True))
