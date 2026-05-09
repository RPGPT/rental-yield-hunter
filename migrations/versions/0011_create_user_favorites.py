"""create_user_favorites
Revision ID: 0011
Revises: 0010
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Optional[str] = "0010"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.create_table(
        "user_favorites",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("listing_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "listing_id"),
    )


def downgrade() -> None:
    op.drop_table("user_favorites")
