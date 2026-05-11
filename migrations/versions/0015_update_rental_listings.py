"""update rental_listings: drop is_rented/lifetime_rent, add rent_price_per_m2

Revision ID: 0015
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Optional[str] = "0014"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.drop_column("rental_listings", "is_rented")
    op.drop_column("rental_listings", "lifetime_rent")
    op.add_column("rental_listings", sa.Column("rent_price_per_m2", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("rental_listings", "rent_price_per_m2")
    op.add_column("rental_listings", sa.Column("lifetime_rent", sa.Boolean(), nullable=True))
    op.add_column("rental_listings", sa.Column("is_rented", sa.Boolean(), nullable=True))
