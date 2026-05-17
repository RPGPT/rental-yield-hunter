"""create rent_contract_details table

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rent_contract_details",
        sa.Column("listing_id", sa.Text(), sa.ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("current_rent", sa.Numeric(10, 2), nullable=True),
        sa.Column("contract_expiry_date", sa.Date(), nullable=True),
        sa.Column("raw_rent_text", sa.Text(), nullable=True),
        sa.Column("raw_expiry_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("extracted_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("rent_contract_details")
