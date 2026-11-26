"""Rental estimate & gross yield computation using a single unified 4-tier CTE waterfall.

Tiers (first tier with ``>= ESTIMATE_MIN_SAMPLES`` active rentals wins):
1. ``typology + neighborhood + area ±15%`` -> confidence ``high``,   match_level ``neighborhood``
2. ``typology + city         + area ±15%`` -> confidence ``medium``, match_level ``city``
3. ``typology + neighborhood``             -> confidence ``medium``, match_level ``neighborhood_broad``
4. ``typology + city``                     -> confidence ``low``,    match_level ``city_broad``
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from yieldhunter.config import ESTIMATE_AREA_TOLERANCE, ESTIMATE_MIN_SAMPLES
from yieldhunter.db.models import RentalEstimate
from yieldhunter.db.repository.common import chunks

logger = logging.getLogger(__name__)

_ESTIMATE_CTE_SQL = """
WITH inputs AS (
    SELECT id, typology, neighborhood, city, area, price
    FROM listings
    WHERE area IS NOT NULL AND typology IS NOT NULL
      {where_clause}
),
t1 AS (
    SELECT i.id,
           AVG(r.rent_price_per_m2)::numeric(10,2) AS avg_rpm,
           COUNT(*)::int                            AS cnt
    FROM inputs i
    JOIN rental_listings r
      ON r.typology     = i.typology
     AND r.neighborhood = i.neighborhood
     AND r.area         BETWEEN i.area * :lo AND i.area * :hi
     AND r.rent_price_per_m2 IS NOT NULL
     AND r.active = true
    GROUP BY i.id
    HAVING COUNT(*) >= :min_samples
),
t2 AS (
    SELECT i.id,
           AVG(r.rent_price_per_m2)::numeric(10,2) AS avg_rpm,
           COUNT(*)::int                            AS cnt
    FROM inputs i
    JOIN rental_listings r
      ON r.typology = i.typology
     AND r.city     = i.city
     AND r.area     BETWEEN i.area * :lo AND i.area * :hi
     AND r.rent_price_per_m2 IS NOT NULL
     AND r.active = true
    GROUP BY i.id
    HAVING COUNT(*) >= :min_samples
),
t3 AS (
    SELECT i.id,
           AVG(r.rent_price_per_m2)::numeric(10,2) AS avg_rpm,
           COUNT(*)::int                            AS cnt
    FROM inputs i
    JOIN rental_listings r
      ON r.typology     = i.typology
     AND r.neighborhood = i.neighborhood
     AND r.rent_price_per_m2 IS NOT NULL
     AND r.active = true
    GROUP BY i.id
    HAVING COUNT(*) >= :min_samples
),
t4 AS (
    SELECT i.id,
           AVG(r.rent_price_per_m2)::numeric(10,2) AS avg_rpm,
           COUNT(*)::int                            AS cnt
    FROM inputs i
    JOIN rental_listings r
      ON r.typology = i.typology
     AND r.city     = i.city
     AND r.rent_price_per_m2 IS NOT NULL
     AND r.active = true
    GROUP BY i.id
    HAVING COUNT(*) >= :min_samples
)
SELECT
    i.id    AS listing_id,
    i.area  AS area,
    i.price AS price,
    COALESCE(t1.avg_rpm, t2.avg_rpm, t3.avg_rpm, t4.avg_rpm)   AS avg_rpm,
    COALESCE(t1.cnt,     t2.cnt,     t3.cnt,     t4.cnt,     0) AS sample_count,
    CASE
        WHEN t1.id IS NOT NULL THEN 'high'
        WHEN t2.id IS NOT NULL THEN 'medium'
        WHEN t3.id IS NOT NULL THEN 'medium'
        WHEN t4.id IS NOT NULL THEN 'low'
        ELSE 'none'
    END AS confidence,
    CASE
        WHEN t1.id IS NOT NULL THEN 'neighborhood'
        WHEN t2.id IS NOT NULL THEN 'city'
        WHEN t3.id IS NOT NULL THEN 'neighborhood_broad'
        WHEN t4.id IS NOT NULL THEN 'city_broad'
        ELSE 'none'
    END AS match_level
FROM inputs i
LEFT JOIN t1 ON t1.id = i.id
LEFT JOIN t2 ON t2.id = i.id
LEFT JOIN t3 ON t3.id = i.id
LEFT JOIN t4 ON t4.id = i.id
"""


def _row_to_estimate(r) -> dict:
    avg_rpm = float(r.avg_rpm) if r.avg_rpm is not None else None
    return {
        "listing_id": r.listing_id,
        "estimated_rent": round(avg_rpm * r.area) if avg_rpm is not None else None,
        "avg_rent_per_m2": avg_rpm,
        "sample_count": r.sample_count,
        "confidence": r.confidence,
        "match_level": r.match_level,
        "rental_yield": round(avg_rpm * r.area * 12 / r.price, 4) if avg_rpm is not None and r.price else None,
    }


def _query_estimates(db: Session, where_clause: str, extra_params: dict) -> list[dict]:
    params = {
        "lo": 1 - ESTIMATE_AREA_TOLERANCE,
        "hi": 1 + ESTIMATE_AREA_TOLERANCE,
        "min_samples": ESTIMATE_MIN_SAMPLES,
        **extra_params,
    }
    rows = db.execute(text(_ESTIMATE_CTE_SQL.format(where_clause=where_clause)), params).fetchall()
    return [_row_to_estimate(r) for r in rows]


def _upsert_estimates(db: Session, estimates: list[dict]) -> int:
    if not estimates:
        return 0
    for chunk in chunks(estimates):
        stmt = insert(RentalEstimate).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["listing_id"],
            set_={
                "estimated_rent": stmt.excluded.estimated_rent,
                "avg_rent_per_m2": stmt.excluded.avg_rent_per_m2,
                "sample_count": stmt.excluded.sample_count,
                "confidence": stmt.excluded.confidence,
                "match_level": stmt.excluded.match_level,
                "rental_yield": stmt.excluded.rental_yield,
                "computed_at": text("NOW()"),
            },
        )
        db.execute(stmt)
    db.commit()
    return len(estimates)


def compute_rental_estimate(db: Session, listing_id: str) -> Optional[dict]:
    """Run the 4-tier waterfall for a single listing ID. Returns ``None`` if inputs are missing."""
    estimates = _query_estimates(db, "AND id = :id", {"id": listing_id})
    return estimates[0] if estimates else None


def compute_and_upsert_rental_estimates(db: Session, listing_ids: list[str]) -> int:
    """Compute and upsert rental estimates for *listing_ids* in a single bulk query."""
    if not listing_ids:
        return 0
    estimates = _query_estimates(db, "AND id = ANY(:ids)", {"ids": listing_ids})
    count = _upsert_estimates(db, estimates)
    if count:
        logger.info("Computed rental estimates for %d listings", count)
    return count


def refresh_rental_estimates(db: Session, city: Optional[str] = None) -> int:
    """Recompute rental estimates for all active, non-deleted buy listings (optionally in *city*)."""
    label = city or "all cities"
    logger.info("Refreshing rental estimates (%s)…", label)

    where_clause = "AND active = true AND is_deleted = false"
    extra_params: dict = {}
    if city:
        where_clause += " AND city = :city"
        extra_params["city"] = city

    estimates = _query_estimates(db, where_clause, extra_params)
    if not estimates:
        logger.info("No eligible listings found (%s)", label)
        return 0

    count = _upsert_estimates(db, estimates)
    logger.info("Refreshed rental estimates for %d listings (%s)", count, label)
    return count
