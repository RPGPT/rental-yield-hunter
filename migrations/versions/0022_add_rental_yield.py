"""add rental_yield to rental_estimates

Revision ID: 0022
Revises: 0021
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Optional[str] = "0021"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.add_column(
        "rental_estimates",
        sa.Column("rental_yield", sa.Numeric(5, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rental_estimates", "rental_yield")
