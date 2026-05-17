"""create user_hidden table

Revision ID: 0018
Revises: 0017
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Optional[str] = "0017"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.create_table(
        "user_hidden",
        sa.Column("user_id", sa.Text(), nullable=False, comment="neon_auth.users.id"),
        sa.Column("listing_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "listing_id"),
    )


def downgrade() -> None:
    op.drop_table("user_hidden")
