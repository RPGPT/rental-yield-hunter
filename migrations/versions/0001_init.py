"""init

Revision ID: 0001
"""
from typing import Optional, Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Optional[str] = None
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.create_table('listings',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('price', sa.Integer(), nullable=True),
    sa.Column('area', sa.Integer(), nullable=True),
    sa.Column('price_per_m2', sa.Float(), nullable=True),
    sa.Column('location', sa.Text(), nullable=True),
    sa.Column('city', sa.Text(), nullable=True),
    sa.Column('parish', sa.Text(), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('property_type', sa.Text(), nullable=True),
    sa.Column('typology', sa.Text(), nullable=True),
    sa.Column('floor', sa.Text(), nullable=True),
    sa.Column('has_elevator', sa.Boolean(), nullable=True),
    sa.Column('has_garage', sa.Boolean(), nullable=True),
    sa.Column('condition', sa.Text(), nullable=True),
    sa.Column('rent_detected', sa.Integer(), nullable=True),
    sa.Column('is_rented', sa.Boolean(), nullable=True),
    sa.Column('first_seen', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.Column('last_seen', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('listing_price_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('listing_id', sa.Text(), nullable=False),
    sa.Column('price', sa.Integer(), nullable=True),
    sa.Column('captured_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('raw_data',
    sa.Column('listing_id', sa.Text(), nullable=False),
    sa.Column('raw_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('raw_html', sa.Text(), nullable=True),
    sa.Column('captured_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ),
    sa.PrimaryKeyConstraint('listing_id')
    )

def downgrade() -> None:
    op.drop_table('raw_data')
    op.drop_table('listing_price_history')
    op.drop_table('listings')
