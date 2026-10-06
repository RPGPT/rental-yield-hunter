from typing import Optional, Sequence

from alembic import op

revision: str = "0028"
down_revision: Optional[str] = "0027"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id BIGSERIAL PRIMARY KEY,
            action TEXT NOT NULL,
            listing_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_email TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log")
