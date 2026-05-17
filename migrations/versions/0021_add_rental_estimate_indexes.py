"""add indexes on rental_listings for estimate tier queries

Revision ID: 0021
Revises: 0020
"""

from typing import Optional, Sequence

from alembic import op

revision: str = "0021"
down_revision: Optional[str] = "0020"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    # Tier 1 & 3: join on typology + neighborhood (+ area range for tier 1)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rental_listings_typology_neighborhood_area
        ON rental_listings (typology, neighborhood, area)
        WHERE active = true AND rent_price_per_m2 IS NOT NULL
    """)
    # Tier 2 & 4: join on typology + city (+ area range for tier 2)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_rental_listings_typology_city_area
        ON rental_listings (typology, city, area)
        WHERE active = true AND rent_price_per_m2 IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_rental_listings_typology_neighborhood_area")
    op.execute("DROP INDEX IF EXISTS idx_rental_listings_typology_city_area")
