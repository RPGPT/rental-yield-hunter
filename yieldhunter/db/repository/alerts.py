"""Database queries and deduplication persistence for saved-search deal alerts."""

from __future__ import annotations

import logging
from datetime import timedelta, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from yieldhunter.analysis.alerts import matches_saved_search
from yieldhunter.db.models import AlertNotification, SavedSearch
from yieldhunter.db.repository.common import chunks

logger = logging.getLogger(__name__)


def _lookup_user_emails(db: Session, user_ids: set[str]) -> dict[str, str]:
    """Look up user emails in ``neon_auth.user`` when that schema exists (prod Neon)."""
    if not user_ids:
        return {}
    exists = db.execute(
        text(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'neon_auth' AND table_name = 'user'
            """
        )
    ).fetchone()
    if not exists:
        return {}
    rows = db.execute(
        text('SELECT id::text AS uid, email FROM neon_auth."user" WHERE id::text = ANY(:uids)'),
        {"uids": list(user_ids)},
    ).fetchall()
    return {r.uid: r.email for r in rows if r.email}


def find_pending_saved_search_alerts(db: Session) -> list[dict]:
    """Evaluate all ``saved_searches`` against new buy listings and recent price drops.

    Returns a list of ``{"saved_search": {...}, "matches": [...]}`` for searches with >=1 match.
    """
    searches = db.query(SavedSearch).order_by(SavedSearch.id).all()
    if not searches:
        return []

    earliest_check = min(s.last_checked_at for s in searches)
    if earliest_check.tzinfo is not None:
        earliest_naive = earliest_check.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        earliest_naive = earliest_check
    query_since = earliest_naive - timedelta(minutes=5)

    # Load candidate active buy listings that are either newly seen or had a price drop since query_since
    candidates = (
        db.execute(
            text(
                """
            WITH recent_drops AS (
                SELECT DISTINCT ON (listing_id)
                    listing_id,
                    previous_price,
                    price AS drop_price,
                    captured_at
                FROM listing_price_history
                WHERE captured_at >= :since
                  AND previous_price IS NOT NULL
                  AND price < previous_price
                ORDER BY listing_id, captured_at DESC, id DESC
            )
            SELECT
                l.id, l.source, l.url, l.title, l.price, l.initial_price,
                l.price_drop_amount, l.price_drop_pct, l.area,
                l.neighborhood, l.city, l.typology, l.has_garage,
                l.is_rented, l.lifetime_rent, l.first_seen,
                re.estimated_rent, re.rental_yield,
                lc.cluster_size, lc.price_spread, lc.is_cheapest,
                rd.previous_price AS drop_previous_price,
                rd.captured_at AS drop_captured_at
            FROM listings l
            LEFT JOIN rental_estimates re ON re.listing_id = l.id
            LEFT JOIN listing_clusters lc ON lc.listing_id = l.id
            LEFT JOIN recent_drops rd ON rd.listing_id = l.id
            WHERE l.active = true AND l.is_deleted = false
              AND (l.first_seen >= :since OR rd.listing_id IS NOT NULL)
            ORDER BY re.rental_yield DESC NULLS LAST, l.price ASC
            """
            ),
            {"since": query_since},
        )
        .mappings()
        .all()
    )

    if not candidates:
        return []

    search_ids = [s.id for s in searches]
    already_sent = {
        (r.saved_search_id, r.listing_id, r.triggered_price)
        for r in db.query(
            AlertNotification.saved_search_id,
            AlertNotification.listing_id,
            AlertNotification.triggered_price,
        )
        .filter(AlertNotification.saved_search_id.in_(search_ids))
        .all()
    }

    user_emails = _lookup_user_emails(db, {s.user_id for s in searches})
    results: list[dict] = []

    for s in searches:
        s_naive = (
            s.last_checked_at.astimezone(timezone.utc).replace(tzinfo=None)
            if s.last_checked_at.tzinfo is not None
            else s.last_checked_at
        )
        s_cutoff = s_naive - timedelta(minutes=5)
        filters = s.filters if isinstance(s.filters, dict) else {}
        matched: list[dict] = []

        for row in candidates:
            if row["price"] is None:
                continue
            if (s.id, row["id"], row["price"]) in already_sent:
                continue

            is_new = row["first_seen"] is not None and row["first_seen"] >= s_cutoff
            is_drop = row["drop_captured_at"] is not None and row["drop_captured_at"] >= s_cutoff
            if not is_new and not is_drop:
                continue

            item = dict(row)
            if not matches_saved_search(item, filters):
                continue

            item["trigger_type"] = "price_drop" if row["drop_captured_at"] is not None else "new"
            item["previous_price"] = row["drop_previous_price"]
            matched.append(item)

        if matched:
            results.append(
                {
                    "saved_search": {
                        "id": s.id,
                        "user_id": s.user_id,
                        "user_email": filters.get("email") or user_emails.get(s.user_id),
                        "name": s.name,
                        "filters": filters,
                    },
                    "matches": matched,
                }
            )

    return results


def record_sent_alerts(db: Session, saved_search_id: int, matches: list[dict]) -> int:
    """Record delivered notifications and advance ``saved_searches.last_checked_at``."""
    rows = [
        {
            "saved_search_id": saved_search_id,
            "listing_id": m["id"],
            "triggered_price": m["price"],
            "trigger_type": m["trigger_type"],
        }
        for m in matches
    ]
    if rows:
        for chunk in chunks(rows):
            stmt = insert(AlertNotification).values(chunk).on_conflict_do_nothing()
            db.execute(stmt)

    db.execute(
        text("UPDATE saved_searches SET last_checked_at = NOW() WHERE id = :id"),
        {"id": saved_search_id},
    )
    db.commit()
    return len(rows)
