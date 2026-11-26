"""Upsert, price-history / price-drop tracking, and scoped deactivation for buy and rental listings."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from yieldhunter.analysis.normalization import normalize_location
from yieldhunter.db.models import (
    Listing,
    ListingPriceHistory,
    RawData,
    RentalListing,
    RentalListingPriceHistory,
    RentalRawData,
)
from yieldhunter.db.repository.common import chunks, sanitize_url

logger = logging.getLogger(__name__)

_EXCLUDE_FROM_INSERT = {"first_seen", "created_at", "is_deleted"}
_EXCLUDE_FROM_UPSERT = {"first_seen", "created_at", "is_deleted", "id", "source"}


def _get_existing(db: Session, ids: list[str], table: str) -> dict:
    """Return ``{id: {price, initial_price, price_change_count, is_deleted, active}}`` for existing rows."""
    if not ids:
        return {}
    rows = db.execute(
        text(
            f"SELECT id, price, initial_price, price_change_count, is_deleted, active FROM {table} WHERE id = ANY(:ids)"
        ),
        {"ids": ids},
    ).fetchall()
    return {
        r[0]: {
            "price": r[1],
            "initial_price": r[2],
            "price_change_count": r[3] or 0,
            "is_deleted": r[4],
            "active": r[5],
        }
        for r in rows
    }


def _compute_price_signals(
    price: Optional[int],
    initial_price: Optional[int],
    change_count: int,
) -> dict:
    if price is not None and initial_price is not None:
        drop_amount = initial_price - price
        drop_pct = round(drop_amount / initial_price, 4) if initial_price > 0 else 0.0
    else:
        drop_amount = None
        drop_pct = None
    return {
        "initial_price": initial_price,
        "price_drop_amount": drop_amount,
        "price_drop_pct": drop_pct,
        "price_change_count": change_count,
    }


def _upsert(
    db: Session,
    listings: list[dict],
    listing_model,
    price_history_model,
    raw_data_model,
) -> int:
    """Generic upsert for buy or rental listings. Returns the number of price changes recorded."""
    if not listings:
        return 0

    for listing in listings:
        if "url" in listing:
            listing["url"] = sanitize_url(listing["url"])
        if "neighborhood" in listing:
            listing["neighborhood"], listing["city"] = normalize_location(listing["neighborhood"], listing.get("city"))

    table = listing_model.__tablename__
    listing_columns = {c.name for c in listing_model.__table__.columns if c.name not in _EXCLUDE_FROM_INSERT}
    upsert_set = [c.name for c in listing_model.__table__.columns if c.name not in _EXCLUDE_FROM_UPSERT]

    existing = _get_existing(db, [listing["id"] for listing in listings], table)

    price_changes = []
    reactivated = []
    clean = []

    for listing in listings:
        price = listing.get("price")
        row = existing.get(listing["id"])
        if row is None:
            signals = _compute_price_signals(price, price, 0)
        elif row["is_deleted"]:
            signals = _compute_price_signals(price, row["initial_price"] or row["price"], row["price_change_count"])
        else:
            init_price = row["initial_price"] if row["initial_price"] is not None else row["price"]
            if init_price is None:
                init_price = price
            change_count = row["price_change_count"]
            if price is not None and row["price"] != price:
                price_changes.append(
                    {
                        "listing_id": listing["id"],
                        "previous_price": row["price"],
                        "price": price,
                    }
                )
                change_count += 1
            if not row["active"]:
                reactivated.append(listing["id"])
                logger.info("Reactivating listing %s — found again after being inactive", listing["id"])
            signals = _compute_price_signals(price, init_price, change_count)

        merged = {**listing, **signals}
        clean.append({k: v for k, v in merged.items() if k in listing_columns})

    for chunk in chunks(clean):
        stmt = insert(listing_model).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={col: getattr(stmt.excluded, col) for col in upsert_set},
            where=listing_model.is_deleted.is_(False),
        )
        db.execute(stmt)

    if price_changes:
        for chunk in chunks(price_changes):
            db.execute(insert(price_history_model).values(chunk))
        logger.info("Recorded %d price changes", len(price_changes))
    if reactivated:
        logger.info("Reactivated %d listings: %s", len(reactivated), reactivated)

    raw_rows = [
        {"listing_id": listing["id"], "raw_json": listing.get("_raw_json")}
        for listing in listings
        if listing.get("_raw_json") and not existing.get(listing["id"], {}).get("is_deleted")
    ]
    if raw_rows:
        for chunk in chunks(raw_rows):
            raw_stmt = insert(raw_data_model).values(chunk)
            raw_stmt = raw_stmt.on_conflict_do_update(
                index_elements=["listing_id"],
                set_={
                    "raw_json": raw_stmt.excluded.raw_json,
                    "captured_at": text("NOW()"),
                },
            )
            db.execute(raw_stmt)

    db.commit()
    return len(price_changes)


def _deactivate_missing(
    db: Session,
    source: str,
    active_ids: list[str],
    listing_model,
    city: Optional[str] = None,
) -> int:
    """Mark as inactive any listing from *source* (scoped to *city*) absent from *active_ids*."""
    table = listing_model.__tablename__
    params: dict = {"source": source, "ids": active_ids}
    city_clause = ""
    if city:
        city_clause = "AND city = :city"
        params["city"] = city

    result = db.execute(
        text(
            f"""
            UPDATE {table}
            SET active = false, inactive_since = NOW()
            WHERE source = :source
              AND active = true
              AND is_deleted = false
              AND id != ALL(:ids)
              {city_clause}
            """
        ),
        params,
    )
    label = f"{source} / {city}" if city else source
    if result.rowcount:
        logger.info("Deactivated %d listings no longer found in %s", result.rowcount, label)
    db.commit()
    return result.rowcount or 0


def upsert_listings(db: Session, listings: list[dict]) -> int:
    return _upsert(db, listings, Listing, ListingPriceHistory, RawData)


def deactivate_missing(db: Session, source: str, active_ids: list[str], city: Optional[str] = None) -> int:
    return _deactivate_missing(db, source, active_ids, Listing, city)


def upsert_rental_listings(db: Session, listings: list[dict]) -> int:
    return _upsert(db, listings, RentalListing, RentalListingPriceHistory, RentalRawData)


def deactivate_missing_rentals(db: Session, source: str, active_ids: list[str], city: Optional[str] = None) -> int:
    return _deactivate_missing(db, source, active_ids, RentalListing, city)


def get_rented_listing_ids(db: Session, city: str, source: str) -> set[str]:
    """Return previously rented listing IDs for one source and city."""
    rows = (
        db.query(Listing.id)
        .filter(
            Listing.is_rented.is_(True),
            Listing.is_deleted.is_(False),
            Listing.city == city,
            Listing.source == source,
        )
        .all()
    )
    return {row.id for row in rows}
