"""add listing_snapshots table

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-10
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_snapshots",
        sa.Column("listing_id", sa.Text(), nullable=False),
        sa.Column("blob_url", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("listing_id"),
    )


def downgrade() -> None:
    op.drop_table("listing_snapshots")
