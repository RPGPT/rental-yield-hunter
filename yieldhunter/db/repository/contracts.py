"""Queries, upserts, and lease-expiry upside computation for ``rent_contract_details``."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from yieldhunter.db.models import Listing, RawData, RentContractDetail
from yieldhunter.db.repository.common import chunks

logger = logging.getLogger(__name__)


def get_rented_listings_for_extraction(db: Session, city: Optional[str] = None) -> list[dict]:
    """Return active, non-deleted rented buy listings together with any stored ``fullDescription``."""
    q = (
        db.query(
            Listing.id,
            Listing.source,
            Listing.city,
            Listing.url,
            Listing.title,
            Listing.description,
            RawData.raw_json,
        )
        .outerjoin(RawData, RawData.listing_id == Listing.id)
        .filter(
            Listing.is_rented.is_(True),
            Listing.active.is_(True),
            Listing.is_deleted.is_(False),
        )
    )
    if city:
        q = q.filter(Listing.city == city)

    rows = []
    for r in q.all():
        raw_json = r.raw_json if isinstance(r.raw_json, dict) else {}
        has_full = "fullDescription" in raw_json
        rows.append(
            {
                "id": r.id,
                "source": r.source,
                "city": r.city,
                "url": r.url or "",
                "title": r.title or "",
                "description": r.description or "",
                "full_description": raw_json.get("fullDescription") or "",
                "has_full_description": has_full,
            }
        )
    return rows


def sync_contract_upside_metrics(db: Session, city: Optional[str] = None) -> int:
    """Recompute Day-1 ``current_yield``, ``reversion_yield``, ``rent_upside_pct``, and ``months_to_expiry``.

    Called at the end of both ``upsert_contract_details`` and ``refresh_rental_estimates`` so
    metrics stay consistent regardless of which pipeline step ran last.
    """
    today = datetime.now(timezone.utc).date()
    city_clause = "AND l.city = :city" if city else ""
    params: dict = {"today": today}
    if city:
        params["city"] = city

    res = db.execute(
        text(
            f"""
            UPDATE rent_contract_details rcd
            SET
                current_yield = CASE
                    WHEN rcd.current_rent IS NOT NULL AND l.price IS NOT NULL AND l.price > 0
                    THEN ROUND((rcd.current_rent * 12.0 / l.price)::numeric, 4)
                    ELSE NULL
                END,
                reversion_yield = CASE
                    WHEN re.estimated_rent IS NOT NULL AND l.price IS NOT NULL AND l.price > 0
                    THEN ROUND((re.estimated_rent * 12.0 / l.price)::numeric, 4)
                    ELSE NULL
                END,
                rent_upside_pct = CASE
                    WHEN rcd.current_rent IS NOT NULL AND rcd.current_rent > 0 AND re.estimated_rent IS NOT NULL
                    THEN ROUND(((re.estimated_rent - rcd.current_rent) / rcd.current_rent)::numeric, 4)
                    ELSE NULL
                END,
                months_to_expiry = CASE
                    WHEN rcd.contract_expiry_date IS NOT NULL
                    THEN (
                        (
                            EXTRACT(YEAR FROM rcd.contract_expiry_date)::int
                            - EXTRACT(YEAR FROM CAST(:today AS date))::int
                        ) * 12
                        + (
                            EXTRACT(MONTH FROM rcd.contract_expiry_date)::int
                            - EXTRACT(MONTH FROM CAST(:today AS date))::int
                        )
                    )
                    ELSE NULL
                END
            FROM listings l
            LEFT JOIN rental_estimates re ON re.listing_id = l.id
            WHERE rcd.listing_id = l.id
              AND l.is_deleted = false
              {city_clause}
            """
        ),
        params,
    )
    db.commit()
    return res.rowcount or 0


def upsert_contract_details(db: Session, details: list[dict], city: Optional[str] = None) -> int:
    """Bulk upsert extracted contract details and refresh lease-upside metrics."""
    if not details:
        return 0

    for chunk in chunks(details):
        stmt = insert(RentContractDetail).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["listing_id"],
            set_={
                "current_rent": stmt.excluded.current_rent,
                "contract_expiry_date": stmt.excluded.contract_expiry_date,
                "raw_rent_text": stmt.excluded.raw_rent_text,
                "raw_expiry_text": stmt.excluded.raw_expiry_text,
                "confidence": stmt.excluded.confidence,
                "updated_at": text("NOW()"),
            },
        )
        db.execute(stmt)
    db.commit()
    sync_contract_upside_metrics(db, city=city)
    logger.info("Upserted %d contract details", len(details))
    return len(details)
