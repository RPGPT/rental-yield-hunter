import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import Listing, ListingPriceHistory, RawData

logger = logging.getLogger(__name__)

LISTING_COLUMNS = [
    c.name for c in Listing.__table__.columns if c.name not in ("first_seen", "created_at", "is_deleted")
]

UPSERT_SET = [
    "url",
    "title",
    "description",
    "price",
    "area",
    "price_per_m2",
    "location",
    "neighborhood",
    "city",
    "property_type",
    "typology",
    "floor",
    "has_garage",
    "is_rented",
    "lifetime_rent",
    "active",
    "inactive_since",
    "last_seen",
    "updated_at",
]


def _sanitize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    return url.replace("/hpr/", "/")


def upsert_listings(db: Session, listings: list[dict]):
    if not listings:
        return

    # Ensure /hpr/ is never stored regardless of what the parser produced
    for listing in listings:
        if "url" in listing:
            listing["url"] = _sanitize_url(listing["url"])

    # Single query: fetch existing price + deleted flag for all incoming IDs
    existing = _get_existing(db, [listing["id"] for listing in listings])

    price_changes = []
    for listing in listings:
        row = existing.get(listing["id"])
        if row and not row["is_deleted"] and listing.get("price") is not None and row["price"] != listing["price"]:
            price_changes.append({"listing_id": listing["id"], "price": listing["price"]})

    clean = [{k: v for k, v in listing.items() if k in LISTING_COLUMNS} for listing in listings]

    stmt = insert(Listing).values(clean)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={col: getattr(stmt.excluded, col) for col in UPSERT_SET},
        # Never touch a row that has been manually deleted
        where=Listing.is_deleted.is_(False),
    )
    db.execute(stmt)

    if price_changes:
        db.execute(insert(ListingPriceHistory).values(price_changes))
        logger.info("Recorded %d price changes", len(price_changes))

    raw_rows = [
        {
            "listing_id": listing["id"],
            "raw_json": listing.get("_raw_json"),
        }
        for listing in listings
        if listing.get("_raw_json")
    ]
    if raw_rows:
        # Filter out deleted listings — don't update raw data for them either
        raw_rows = [r for r in raw_rows if not existing.get(r["listing_id"], {}).get("is_deleted")]
    if raw_rows:
        raw_stmt = insert(RawData).values(raw_rows)
        raw_stmt = raw_stmt.on_conflict_do_update(
            index_elements=["listing_id"],
            set_={
                "raw_json": raw_stmt.excluded.raw_json,
                "captured_at": text("NOW()"),
            },
        )
        db.execute(raw_stmt)

    db.commit()


def _get_existing(db: Session, ids: list[str]) -> dict:
    """Return {id: {price, is_deleted}} for all ids that already exist."""
    if not ids:
        return {}
    rows = db.execute(
        text("SELECT id, price, is_deleted FROM listings WHERE id = ANY(:ids)"),
        {"ids": ids},
    ).fetchall()
    return {r[0]: {"price": r[1], "is_deleted": r[2]} for r in rows}


def deactivate_missing(db: Session, source: str, active_ids: list[str]):
    result = db.execute(
        text("""
            UPDATE listings
            SET active = false, inactive_since = NOW()
            WHERE source = :source
              AND active = true
              AND is_deleted = false
              AND id != ALL(:ids)
        """),
        {"source": source, "ids": active_ids},
    )
    if result.rowcount:
        logger.info("Deactivated %d listings no longer found in %s", result.rowcount, source)
    db.commit()
