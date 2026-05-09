"""drop raw_html from raw_data
Revision ID: 0012
Revises: 0011
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Optional[str] = "0011"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.drop_column("raw_data", "raw_html")


def downgrade() -> None:
    op.add_column("raw_data", sa.Column("raw_html", sa.Text(), nullable=True))
