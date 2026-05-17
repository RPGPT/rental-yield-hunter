"""widen rental_yield to numeric(8,4)

Revision ID: 0023
Revises: 0022
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Optional[str] = "0022"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.alter_column(
        "rental_estimates",
        "rental_yield",
        type_=sa.Numeric(8, 4),
        existing_type=sa.Numeric(5, 4),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "rental_estimates",
        "rental_yield",
        type_=sa.Numeric(5, 4),
        existing_type=sa.Numeric(8, 4),
        existing_nullable=True,
    )
