"""Add lease-upside metrics, price-drop tracking, listing_clusters, and alert_notifications.

Revision ID: 0030
Revises: 0029
"""

from typing import Optional, Sequence

from alembic import op

revision: str = "0030"
down_revision: Optional[str] = "0029"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    # ── #3: Price history previous_price + motivated-seller columns ──────────
    op.execute("ALTER TABLE listing_price_history ADD COLUMN IF NOT EXISTS previous_price INTEGER")
    op.execute("ALTER TABLE rental_listing_price_history ADD COLUMN IF NOT EXISTS previous_price INTEGER")

    op.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS initial_price INTEGER")
    op.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS price_drop_amount INTEGER")
    op.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS price_drop_pct NUMERIC(8, 4)")
    op.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS price_change_count INTEGER NOT NULL DEFAULT 0")

    op.execute("ALTER TABLE rental_listings ADD COLUMN IF NOT EXISTS initial_price INTEGER")
    op.execute("ALTER TABLE rental_listings ADD COLUMN IF NOT EXISTS price_drop_amount INTEGER")
    op.execute("ALTER TABLE rental_listings ADD COLUMN IF NOT EXISTS price_drop_pct NUMERIC(8, 4)")
    op.execute("ALTER TABLE rental_listings ADD COLUMN IF NOT EXISTS price_change_count INTEGER NOT NULL DEFAULT 0")

    # Backfill initial_price, price_change_count, price_drop_amount, and price_drop_pct
    for tbl, hist_tbl in (
        ("listings", "listing_price_history"),
        ("rental_listings", "rental_listing_price_history"),
    ):
        op.execute(
            f"""
            WITH hist_stats AS (
                SELECT
                    listing_id,
                    COUNT(*)::int AS cnt,
                    (ARRAY_AGG(COALESCE(previous_price, price) ORDER BY captured_at ASC, id ASC))[1] AS earliest_price
                FROM {hist_tbl}
                GROUP BY listing_id
            )
            UPDATE {tbl} l
            SET
                initial_price = COALESCE(l.initial_price, hs.earliest_price, l.price),
                price_change_count = COALESCE(hs.cnt, 0)
            FROM (SELECT id FROM {tbl}) all_ids
            LEFT JOIN hist_stats hs ON hs.listing_id = all_ids.id
            WHERE l.id = all_ids.id AND l.initial_price IS NULL
            """
        )
        op.execute(
            f"""
            UPDATE {tbl}
            SET
                price_drop_amount = CASE
                    WHEN initial_price IS NOT NULL AND price IS NOT NULL THEN initial_price - price
                    ELSE NULL
                END,
                price_drop_pct = CASE
                    WHEN initial_price IS NOT NULL AND initial_price > 0 AND price IS NOT NULL
                    THEN ROUND(((initial_price - price)::numeric / initial_price), 4)
                    ELSE NULL
                END
            WHERE price_drop_amount IS NULL AND initial_price IS NOT NULL AND price IS NOT NULL
            """
        )

    # ── #2: Lease-expiry upside metrics on rent_contract_details ─────────────
    op.execute("ALTER TABLE rent_contract_details ADD COLUMN IF NOT EXISTS current_yield NUMERIC(8, 4)")
    op.execute("ALTER TABLE rent_contract_details ADD COLUMN IF NOT EXISTS reversion_yield NUMERIC(8, 4)")
    op.execute("ALTER TABLE rent_contract_details ADD COLUMN IF NOT EXISTS rent_upside_pct NUMERIC(8, 4)")
    op.execute("ALTER TABLE rent_contract_details ADD COLUMN IF NOT EXISTS months_to_expiry INTEGER")

    # ── #5: Cross-source / multi-agency deduplication & price arbitrage ──────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_clusters (
            listing_id TEXT PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
            cluster_id TEXT NOT NULL,
            cluster_size INTEGER NOT NULL,
            cluster_min_price INTEGER NOT NULL,
            cluster_max_price INTEGER NOT NULL,
            price_spread INTEGER NOT NULL,
            price_spread_pct NUMERIC(8, 4) NOT NULL,
            is_cheapest BOOLEAN NOT NULL DEFAULT true,
            sources JSONB NOT NULL DEFAULT '[]'::jsonb,
            computed_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_listing_clusters_cluster_id ON listing_clusters (cluster_id)")

    # ── #6: Automated saved-search deal alert dedup log ──────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_notifications (
            saved_search_id BIGINT NOT NULL REFERENCES saved_searches(id) ON DELETE CASCADE,
            listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
            triggered_price INTEGER NOT NULL,
            trigger_type TEXT NOT NULL,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (saved_search_id, listing_id, triggered_price)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_notifications")
    op.execute("DROP INDEX IF EXISTS ix_listing_clusters_cluster_id")
    op.execute("DROP TABLE IF EXISTS listing_clusters")

    op.execute("ALTER TABLE rent_contract_details DROP COLUMN IF EXISTS months_to_expiry")
    op.execute("ALTER TABLE rent_contract_details DROP COLUMN IF EXISTS rent_upside_pct")
    op.execute("ALTER TABLE rent_contract_details DROP COLUMN IF EXISTS reversion_yield")
    op.execute("ALTER TABLE rent_contract_details DROP COLUMN IF EXISTS current_yield")

    op.execute("ALTER TABLE rental_listings DROP COLUMN IF EXISTS price_change_count")
    op.execute("ALTER TABLE rental_listings DROP COLUMN IF EXISTS price_drop_pct")
    op.execute("ALTER TABLE rental_listings DROP COLUMN IF EXISTS price_drop_amount")
    op.execute("ALTER TABLE rental_listings DROP COLUMN IF EXISTS initial_price")

    op.execute("ALTER TABLE listings DROP COLUMN IF EXISTS price_change_count")
    op.execute("ALTER TABLE listings DROP COLUMN IF EXISTS price_drop_pct")
    op.execute("ALTER TABLE listings DROP COLUMN IF EXISTS price_drop_amount")
    op.execute("ALTER TABLE listings DROP COLUMN IF EXISTS initial_price")

    op.execute("ALTER TABLE rental_listing_price_history DROP COLUMN IF EXISTS previous_price")
    op.execute("ALTER TABLE listing_price_history DROP COLUMN IF EXISTS previous_price")
