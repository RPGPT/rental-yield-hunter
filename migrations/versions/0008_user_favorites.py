"""user_favorites
Revision ID: 0008
Revises: 0007
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Optional[str] = "0007"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    # Remove is_favorite from listings — favourites are now user-scoped
    op.drop_column("listings", "is_favorite")

    # Users table (populated on Google OAuth login)
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), nullable=False),  # Google OAuth 'sub'
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("picture", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # Junction table: one row per (user, listing) pair
    op.create_table(
        "user_favorites",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("listing_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "listing_id"),
    )


def downgrade() -> None:
    op.drop_table("user_favorites")
    op.drop_table("users")
    op.add_column("listings", sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default="false"))
