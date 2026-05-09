"""add_is_deleted
Revision ID: 0007
Revises: 0006
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Optional[str] = "0006"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("listings", "is_deleted")
