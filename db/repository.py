import json
import logging
from typing import List

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import Listing, ListingPriceHistory, RawData

logger = logging.getLogger(__name__)

LISTING_COLUMNS = [
    c.name for c in Listing.__table__.columns
    if c.name not in ("first_seen", "created_at")
]

UPSERT_SET = [
    "title", "description", "price", "area", "price_per_m2",
    "location", "city", "parish", "latitude", "longitude",
    "property_type", "typology", "floor",
    "has_elevator", "has_garage", "condition",
    "is_rented", "last_seen", "updated_at",
]


def upsert_listings(db: Session, listings: List[dict]):
    if not listings:
        return

    existing_prices = _get_current_prices(db, [l["id"] for l in listings])

    price_changes = []
    for l in listings:
        old_price = existing_prices.get(l["id"])
        if old_price is not None and l.get("price") is not None and old_price != l["price"]:
            price_changes.append({"listing_id": l["id"], "price": l["price"]})

    clean = [{k: v for k, v in l.items() if k in LISTING_COLUMNS} for l in listings]

    stmt = insert(Listing).values(clean)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={col: getattr(stmt.excluded, col) for col in UPSERT_SET},
    )
    db.execute(stmt)

    if price_changes:
        db.execute(insert(ListingPriceHistory).values(price_changes))
        logger.info("Recorded %d price changes", len(price_changes))

    raw_rows = [
        {"listing_id": l["id"], "raw_json": l.get("_raw_json")}
        for l in listings if l.get("_raw_json")
    ]
    if raw_rows:
        raw_stmt = insert(RawData).values(raw_rows)
        raw_stmt = raw_stmt.on_conflict_do_update(
            index_elements=["listing_id"],
            set_={"raw_json": raw_stmt.excluded.raw_json, "captured_at": text("NOW()")},
        )
        db.execute(raw_stmt)

    db.commit()


def _get_current_prices(db: Session, ids: List[str]) -> dict:
    if not ids:
        return {}
    rows = db.execute(
        text("SELECT id, price FROM listings WHERE id = ANY(:ids)"),
        {"ids": ids},
    ).fetchall()
    return {r[0]: r[1] for r in rows}
