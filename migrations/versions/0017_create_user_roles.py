"""create user_roles table

Simple table linking a neon_auth user ID to a role.
No FK enforced at DB level (neon_auth.users lives in a separate schema),
same pattern as user_favorites.

Revision ID: 0017
Revises: 0016
"""

from typing import Optional, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Optional[str] = "0016"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Text(), nullable=False, comment="neon_auth.users.id"),
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
            server_default="user",
            comment="'user' or 'admin'",
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.CheckConstraint("role IN ('user', 'admin')", name="user_roles_role_check"),
    )


def downgrade() -> None:
    op.drop_table("user_roles")
