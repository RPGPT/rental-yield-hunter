from typing import Optional, Sequence

from alembic import op

revision: str = "0029"
down_revision: Optional[str] = "0028"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_searches (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            filters JSONB NOT NULL DEFAULT '{}'::jsonb,
            last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_saved_searches_user_id ON saved_searches (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saved_searches")
