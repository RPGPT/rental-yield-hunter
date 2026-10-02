"""use the city name when the neighborhood is generic or missing

Revision ID: 0027
Revises: 0026
"""

from typing import Optional, Sequence

from alembic import op
from sqlalchemy import text

from normalization import normalize_location

revision: str = "0027"
down_revision: Optional[str] = "0026"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    conn = op.get_bind()
    for table in ("listings", "rental_listings"):
        rows = conn.execute(text(f"SELECT DISTINCT city, neighborhood FROM {table} WHERE city IS NOT NULL")).fetchall()
        for city, raw in rows:
            canon, _ = normalize_location(raw, city)
            if canon == raw:
                continue
            cond = "neighborhood IS NULL" if raw is None else "neighborhood = :raw"
            conn.execute(
                text(f"UPDATE {table} SET neighborhood = :n WHERE city = :c AND {cond}"),
                {"n": canon, "c": city, "raw": raw},
            )


def downgrade() -> None:
    pass
