"""user_favorites: drop FK so rental listing IDs can be stored

buy listing IDs are small integers; rental listing IDs are large bigints
(e.g. 91914162500067) that don't exist in the buy listings table, causing
FK violations. Drop the constraint — JOINs remain correct because buy and
rental IDs don't overlap. listing_id is already TEXT so no widening needed.

Revision ID: 0016
"""

from typing import Optional, Sequence

from alembic import op

revision: str = "0016"
down_revision: Optional[str] = "0015"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.drop_constraint("user_favorites_listing_id_fkey", "user_favorites", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key(
        "user_favorites_listing_id_fkey",
        "user_favorites",
        "listings",
        ["listing_id"],
        ["id"],
        ondelete="CASCADE",
    )
