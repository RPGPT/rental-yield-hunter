"""drop user_roles table

Revision ID: 0019
Revises: 0018
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Optional[str] = "0018"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.drop_table("user_roles")


def downgrade() -> None:
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Text(), nullable=False, comment="neon_auth.users.id"),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'user'")),
        sa.PrimaryKeyConstraint("user_id"),
        sa.CheckConstraint("role IN ('user', 'admin')", name="user_roles_role_check"),
    )
