"""Deterministic DB snapshot helper for comparing pipeline outputs before and after refactoring."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session


def _num(val):
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, float):
        return round(val, 4)
    return val


def dump_db_snapshot(db: Session) -> dict:
    """Dump all pipeline-written tables in a deterministic, timestamp-independent form."""
    buy_rows = db.execute(
        text(
            """
            SELECT id, source, url, title, description, price, area, price_per_m2,
                   location, neighborhood, city, property_type, typology, floor,
                   has_garage, is_rented, lifetime_rent, is_deleted, active,
                   (inactive_since IS NOT NULL) AS has_inactive_since
            FROM listings
            ORDER BY id
            """
        )
    ).mappings()

    buy_raw = {
        r["listing_id"]: {
            "has_raw": r["raw_json"] is not None,
            "has_full_description": isinstance(r["raw_json"], dict) and "fullDescription" in r["raw_json"],
        }
        for r in db.execute(text("SELECT listing_id, raw_json FROM raw_data ORDER BY listing_id")).mappings()
    }

    buy_history = [
        {"listing_id": r["listing_id"], "price": r["price"]}
        for r in db.execute(
            text("SELECT listing_id, price FROM listing_price_history ORDER BY listing_id, id")
        ).mappings()
    ]

    rent_rows = db.execute(
        text(
            """
            SELECT id, source, url, title, description, price, area, price_per_m2, rent_price_per_m2,
                   location, neighborhood, city, property_type, typology, floor,
                   has_garage, is_deleted, active,
                   (inactive_since IS NOT NULL) AS has_inactive_since
            FROM rental_listings
            ORDER BY id
            """
        )
    ).mappings()

    rent_raw = {
        r["listing_id"]: {"has_raw": r["raw_json"] is not None}
        for r in db.execute(text("SELECT listing_id, raw_json FROM rental_raw_data ORDER BY listing_id")).mappings()
    }

    rent_history = [
        {"listing_id": r["listing_id"], "price": r["price"]}
        for r in db.execute(
            text("SELECT listing_id, price FROM rental_listing_price_history ORDER BY listing_id, id")
        ).mappings()
    ]

    estimates = [
        {
            "listing_id": r["listing_id"],
            "estimated_rent": r["estimated_rent"],
            "avg_rent_per_m2": _num(r["avg_rent_per_m2"]),
            "sample_count": r["sample_count"],
            "confidence": r["confidence"],
            "match_level": r["match_level"],
            "rental_yield": _num(r["rental_yield"]),
        }
        for r in db.execute(
            text(
                """
                SELECT listing_id, estimated_rent, avg_rent_per_m2, sample_count,
                       confidence, match_level, rental_yield
                FROM rental_estimates
                ORDER BY listing_id
                """
            )
        ).mappings()
    ]

    contracts = [
        {
            "listing_id": r["listing_id"],
            "current_rent": _num(r["current_rent"]),
            "contract_expiry_date": r["contract_expiry_date"].isoformat() if r["contract_expiry_date"] else None,
            "raw_rent_text": r["raw_rent_text"],
            "raw_expiry_text": r["raw_expiry_text"],
            "confidence": _num(r["confidence"]),
        }
        for r in db.execute(
            text(
                """
                SELECT listing_id, current_rent, contract_expiry_date,
                       raw_rent_text, raw_expiry_text, confidence
                FROM rent_contract_details
                ORDER BY listing_id
                """
            )
        ).mappings()
    ]

    def _clean(row_mapping) -> dict:
        d = dict(row_mapping)
        for k in ("price_per_m2", "rent_price_per_m2"):
            if k in d:
                d[k] = _num(d[k])
        return d

    return {
        "listings": [_clean(r) for r in buy_rows],
        "raw_data": buy_raw,
        "listing_price_history": buy_history,
        "rental_listings": [_clean(r) for r in rent_rows],
        "rental_raw_data": rent_raw,
        "rental_listing_price_history": rent_history,
        "rental_estimates": estimates,
        "rent_contract_details": contracts,
    }
