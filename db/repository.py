import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import (
    Listing,
    ListingPriceHistory,
    RawData,
    RentalEstimate,
    RentalListing,
    RentalListingPriceHistory,
    RentalRawData,
)

logger = logging.getLogger(__name__)

_EXCLUDE_FROM_INSERT = {"first_seen", "created_at", "is_deleted"}
_EXCLUDE_FROM_UPSERT = {"first_seen", "created_at", "is_deleted", "id", "source"}


def _sanitize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    return url.replace("/hpr/", "/")


def _get_existing(db: Session, ids: list[str], table: str) -> dict:
    """Return {id: {price, is_deleted, active}} for all ids that already exist."""
    if not ids:
        return {}
    rows = db.execute(
        text(f"SELECT id, price, is_deleted, active FROM {table} WHERE id = ANY(:ids)"),
        {"ids": ids},
    ).fetchall()
    return {r[0]: {"price": r[1], "is_deleted": r[2], "active": r[3]} for r in rows}


def _upsert(
    db: Session,
    listings: list[dict],
    listing_model,
    price_history_model,
    raw_data_model,
) -> int:
    """Generic upsert for any listing model. Returns the number of price changes recorded."""
    if not listings:
        return 0

    for listing in listings:
        if "url" in listing:
            listing["url"] = _sanitize_url(listing["url"])

    table = listing_model.__tablename__
    listing_columns = [c.name for c in listing_model.__table__.columns if c.name not in _EXCLUDE_FROM_INSERT]
    upsert_set = [c.name for c in listing_model.__table__.columns if c.name not in _EXCLUDE_FROM_UPSERT]

    existing = _get_existing(db, [listing["id"] for listing in listings], table)

    price_changes = []
    reactivated = []
    for listing in listings:
        row = existing.get(listing["id"])
        if row and not row["is_deleted"]:
            if listing.get("price") is not None and row["price"] != listing["price"]:
                price_changes.append({"listing_id": listing["id"], "price": listing["price"]})
            if not row["active"]:
                reactivated.append(listing["id"])
                logger.info("Reactivating listing %s — found again after being inactive", listing["id"])

    clean = [{k: v for k, v in listing.items() if k in listing_columns} for listing in listings]

    stmt = insert(listing_model).values(clean)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={col: getattr(stmt.excluded, col) for col in upsert_set},
        # Never touch a row that has been manually deleted
        where=listing_model.is_deleted.is_(False),
    )
    db.execute(stmt)

    if price_changes:
        db.execute(insert(price_history_model).values(price_changes))
        logger.info("Recorded %d price changes", len(price_changes))
    if reactivated:
        logger.info("Reactivated %d listings: %s", len(reactivated), reactivated)

    raw_rows = [
        {"listing_id": listing["id"], "raw_json": listing.get("_raw_json")}
        for listing in listings
        if listing.get("_raw_json")
    ]
    if raw_rows:
        raw_rows = [r for r in raw_rows if not existing.get(r["listing_id"], {}).get("is_deleted")]
    if raw_rows:
        raw_stmt = insert(raw_data_model).values(raw_rows)
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
) -> None:
    """Mark as inactive any listing from *source* (optionally scoped to *city*)
    that was not present in the current scrape run.
    """
    table = listing_model.__tablename__
    params: dict = {"source": source, "ids": active_ids}
    city_clause = ""
    if city:
        city_clause = "AND city = :city"
        params["city"] = city

    result = db.execute(
        text(f"""
            UPDATE {table}
            SET active = false, inactive_since = NOW()
            WHERE source = :source
              AND active = true
              AND is_deleted = false
              AND id != ALL(:ids)
              {city_clause}
        """),
        params,
    )
    label = f"{source} / {city}" if city else source
    if result.rowcount:
        logger.info("Deactivated %d listings no longer found in %s", result.rowcount, label)
    db.commit()


# ── Buy listings ────────────────────────────────────────────────────────────


def upsert_listings(db: Session, listings: list[dict]) -> int:
    """Upsert buy listings and return the number of price changes recorded."""
    return _upsert(db, listings, Listing, ListingPriceHistory, RawData)


def deactivate_missing(db: Session, source: str, active_ids: list[str], city: Optional[str] = None) -> None:
    """Mark as inactive any buy listing from *source* not present in the current scrape run.

    Passing *city* is strongly recommended when scraping cities in parallel —
    without it the UPDATE touches rows belonging to all cities of that source,
    causing race conditions and incorrect deactivations.
    """
    _deactivate_missing(db, source, active_ids, Listing, city)


# ── Rental listings ─────────────────────────────────────────────────────────


def upsert_rental_listings(db: Session, listings: list[dict]) -> int:
    """Upsert rental listings and return the number of price changes recorded."""
    return _upsert(db, listings, RentalListing, RentalListingPriceHistory, RentalRawData)


def deactivate_missing_rentals(db: Session, source: str, active_ids: list[str], city: Optional[str] = None) -> None:
    """Mark as inactive any rental listing from *source* not present in the current scrape run."""
    _deactivate_missing(db, source, active_ids, RentalListing, city)


# ── Rental estimates ─────────────────────────────────────────────────────────

_MIN_SAMPLES = 3
_AREA_TOLERANCE = 0.15

_TIERS = [
    {
        "where": """
            typology = :typology
            AND neighborhood = :neighborhood
            AND area BETWEEN :area_min AND :area_max
        """,
        "params": lambda t, n, c, lo, hi: {"typology": t, "neighborhood": n, "area_min": lo, "area_max": hi},
        "confidence": "high",
        "match_level": "neighborhood",
    },
    {
        "where": """
            typology = :typology
            AND city = :city
            AND area BETWEEN :area_min AND :area_max
        """,
        "params": lambda t, n, c, lo, hi: {"typology": t, "city": c, "area_min": lo, "area_max": hi},
        "confidence": "medium",
        "match_level": "city",
    },
    {
        "where": "typology = :typology AND neighborhood = :neighborhood",
        "params": lambda t, n, c, lo, hi: {"typology": t, "neighborhood": n},
        "confidence": "medium",
        "match_level": "neighborhood_broad",
    },
    {
        "where": "typology = :typology AND city = :city",
        "params": lambda t, n, c, lo, hi: {"typology": t, "city": c},
        "confidence": "low",
        "match_level": "city_broad",
    },
]


def compute_rental_estimate(db: Session, listing_id: str) -> Optional[dict]:
    """Run the tier waterfall and return an estimate dict, or None if inputs are missing."""
    row = db.execute(
        text("SELECT typology, neighborhood, city, area FROM listings WHERE id = :id"),
        {"id": listing_id},
    ).fetchone()

    if row is None:
        return None

    typology, neighborhood, city, area = row

    if area is None or typology is None:
        return None

    area_min = area * (1 - _AREA_TOLERANCE)
    area_max = area * (1 + _AREA_TOLERANCE)

    for tier in _TIERS:
        params = tier["params"](typology, neighborhood, city, area_min, area_max)
        result = db.execute(
            text(f"""
                SELECT AVG(rent_price_per_m2)::numeric(10,2) AS avg_rent_per_m2,
                       COUNT(*)::int                          AS sample_count
                FROM rental_listings
                WHERE {tier["where"]}
                  AND rent_price_per_m2 IS NOT NULL
                  AND active = true
            """),
            params,
        ).fetchone()

        if result and result.sample_count >= _MIN_SAMPLES:
            avg = float(result.avg_rent_per_m2)
            return {
                "listing_id": listing_id,
                "estimated_rent": round(avg * area),
                "avg_rent_per_m2": avg,
                "sample_count": result.sample_count,
                "confidence": tier["confidence"],
                "match_level": tier["match_level"],
            }

    return {
        "listing_id": listing_id,
        "estimated_rent": None,
        "avg_rent_per_m2": None,
        "sample_count": 0,
        "confidence": "none",
        "match_level": "none",
    }


def compute_and_upsert_rental_estimates(db: Session, listing_ids: list[str]) -> int:
    """Compute rental estimates for the given buy listing IDs and persist them. Returns count."""
    if not listing_ids:
        return 0

    estimates = []
    for listing_id in listing_ids:
        estimate = compute_rental_estimate(db, listing_id)
        if estimate is not None:
            estimates.append(estimate)

    if not estimates:
        return 0

    stmt = insert(RentalEstimate).values(estimates)
    stmt = stmt.on_conflict_do_update(
        index_elements=["listing_id"],
        set_={
            "estimated_rent": stmt.excluded.estimated_rent,
            "avg_rent_per_m2": stmt.excluded.avg_rent_per_m2,
            "sample_count": stmt.excluded.sample_count,
            "confidence": stmt.excluded.confidence,
            "match_level": stmt.excluded.match_level,
            "computed_at": text("NOW()"),
        },
    )
    db.execute(stmt)
    db.commit()
    logger.info("Computed rental estimates for %d listings", len(estimates))
    return len(estimates)


def refresh_rental_estimates(db: Session) -> int:
    """Recompute rental estimates for ALL active, non-deleted buy listings in the DB.

    Always covers every city — call this after any rental scrape run,
    regardless of which city subset was scraped.
    """
    rows = db.execute(text("SELECT id FROM listings WHERE active = true AND is_deleted = false")).fetchall()
    listing_ids = [r[0] for r in rows]
    logger.info("Refreshing rental estimates for %d active listings", len(listing_ids))
    return compute_and_upsert_rental_estimates(db, listing_ids)
