"""Queries and upserts for ``rent_contract_details``."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from yieldhunter.db.models import Listing, RawData, RentContractDetail
from yieldhunter.db.repository.common import chunks

logger = logging.getLogger(__name__)


def get_rented_listings_for_extraction(db: Session, city: Optional[str] = None) -> list[dict]:
    """Return active, non-deleted rented buy listings together with any stored ``fullDescription``.

    Joining ``raw_data`` avoids redundant HTTP detail fetches for listings that were already
    enriched during ``scrape_city``.
    """
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


def upsert_contract_details(db: Session, details: list[dict]) -> int:
    """Bulk upsert extracted contract details."""
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
    logger.info("Upserted %d contract details", len(details))
    return len(details)
