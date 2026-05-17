"""create rental_estimates table

Revision ID: 0020
Revises: 0019
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Optional[str] = "0019"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.create_table(
        "rental_estimates",
        sa.Column("listing_id", sa.Text(), nullable=False),
        sa.Column("estimated_rent", sa.Integer(), nullable=True),
        sa.Column("avg_rent_per_m2", sa.Numeric(10, 2), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("match_level", sa.Text(), nullable=True),
        sa.Column("computed_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("listing_id"),
    )


def downgrade() -> None:
    op.drop_table("rental_estimates")
