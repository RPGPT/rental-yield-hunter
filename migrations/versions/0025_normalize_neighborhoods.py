"""normalize neighborhood names and cities on existing listings

Revision ID: 0025
Revises: 0024
"""

from typing import Optional, Sequence

from alembic import op
from sqlalchemy import text

from normalization import _LOOKUP, _NEIGHBORHOOD_CITY

revision: str = "0025"
down_revision: Optional[str] = "0024"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    conn = op.get_bind()
    for table in ("listings", "rental_listings"):
        rows = conn.execute(
            text(f"SELECT DISTINCT neighborhood FROM {table} WHERE neighborhood IS NOT NULL")
        ).fetchall()
        for (raw,) in rows:
            canon = _LOOKUP.get(raw.strip().casefold(), raw.strip())
            city = _NEIGHBORHOOD_CITY.get(canon)
            if canon == raw and city is None:
                continue
            conn.execute(
                text(f"UPDATE {table} SET neighborhood = :n, city = COALESCE(:c, city) WHERE neighborhood = :raw"),
                {"n": canon, "c": city, "raw": raw},
            )


def downgrade() -> None:
    pass
