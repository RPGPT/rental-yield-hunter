"""Non-linear rental estimate & gross yield computation (Size-Curved Weighted-Median Comps).

Why non-linear?
Rent per m² diminishes sharply with apartment size (in Porto data, ``rent ∝ area^0.30`` within
the same neighborhood and typology). Multiplying ``AVG(rent_price_per_m2) * area`` linearly
overestimates large apartments and is skewed by luxury outliers.

Model (Method 1B):
1. Pool active rentals plus rentals deactivated within the last ``ESTIMATE_INACTIVE_DAYS`` (60d),
   down-weighted by ``ESTIMATE_INACTIVE_WEIGHT`` (0.60).
2. Prefer ``(city, neighborhood, typology)`` when ``>= ESTIMATE_MIN_SAMPLES`` (3) comps exist
   (staying in the same parish before falling back to city-wide comps); otherwise use ``(city, typology)``.
3. Adjust each comparable's rent along the empirical diminishing-returns size curve:
   ``adjusted_rent = comp_rent * (target_area / comp_area) ** ESTIMATE_AREA_EXPONENT``.
4. Compute the **weighted median** of ``adjusted_rent``, weighting by parish match, Gaussian
   log-area similarity (``ESTIMATE_AREA_SIGMA``), and recency.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from yieldhunter.config import (
    ESTIMATE_AREA_EXPONENT,
    ESTIMATE_AREA_SIGMA,
    ESTIMATE_AREA_TOLERANCE,
    ESTIMATE_INACTIVE_DAYS,
    ESTIMATE_INACTIVE_WEIGHT,
    ESTIMATE_MIN_SAMPLES,
    ESTIMATE_OTHER_PARISH_WEIGHT,
)
from yieldhunter.db.models import RentalEstimate
from yieldhunter.db.repository.common import chunks

logger = logging.getLogger(__name__)


def _weighted_median(values_weights: list[tuple[float, float]]) -> float:
    pairs = sorted(values_weights, key=lambda x: x[0])
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return pairs[len(pairs) // 2][0]
    half = total_w * 0.5
    acc = 0.0
    for val, w in pairs:
        acc += w
        if acc >= half:
            return val
    return pairs[-1][0]


def _load_comparable_pools(
    db: Session,
    cities: Optional[set[str]] = None,
) -> tuple[dict[tuple[str, Optional[str], str], list[dict]], dict[tuple[str, str], list[dict]]]:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=ESTIMATE_INACTIVE_DAYS)
    city_clause = "AND city = ANY(:cities)" if cities else ""
    params: dict = {"cutoff": cutoff}
    if cities:
        params["cities"] = list(cities)

    rows = db.execute(
        text(
            f"""
            SELECT city, neighborhood, typology, area, rent_price_per_m2, active
            FROM rental_listings
            WHERE is_deleted = false
              AND area IS NOT NULL AND area > 0
              AND typology IS NOT NULL
              AND city IS NOT NULL
              AND rent_price_per_m2 IS NOT NULL AND rent_price_per_m2 > 0
              AND (active = true OR (inactive_since IS NOT NULL AND inactive_since >= :cutoff))
              {city_clause}
            """
        ),
        params,
    ).fetchall()

    by_nt: dict[tuple[str, Optional[str], str], list[dict]] = defaultdict(list)
    by_ct: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        comp = {
            "neighborhood": r.neighborhood,
            "area": float(r.area),
            "rent": float(r.rent_price_per_m2) * float(r.area),
            "recency_w": 1.0 if r.active else ESTIMATE_INACTIVE_WEIGHT,
        }
        by_nt[(r.city, r.neighborhood, r.typology)].append(comp)
        by_ct[(r.city, r.typology)].append(comp)

    return by_nt, by_ct


def _estimate_one(
    listing_id: str,
    typology: Optional[str],
    neighborhood: Optional[str],
    city: Optional[str],
    area: Optional[int],
    price: Optional[int],
    by_nt: dict[tuple[str, Optional[str], str], list[dict]],
    by_ct: dict[tuple[str, str], list[dict]],
) -> Optional[dict]:
    if area is None or area <= 0 or typology is None:
        return None

    target_area = float(area)
    lo = target_area * (1.0 - ESTIMATE_AREA_TOLERANCE)
    hi = target_area * (1.0 + ESTIMATE_AREA_TOLERANCE)

    nt = by_nt.get((city, neighborhood, typology), []) if city else []
    ct = by_ct.get((city, typology), []) if city else []

    if len(nt) >= ESTIMATE_MIN_SAMPLES:
        pool = nt
        close_count = sum(1 for c in nt if lo <= c["area"] <= hi)
        if close_count >= ESTIMATE_MIN_SAMPLES:
            confidence, match_level = "high", "neighborhood"
        else:
            confidence, match_level = "medium", "neighborhood_broad"
    elif len(ct) >= ESTIMATE_MIN_SAMPLES:
        pool = ct
        close_count = sum(1 for c in ct if lo <= c["area"] <= hi)
        if close_count >= ESTIMATE_MIN_SAMPLES:
            confidence, match_level = "medium", "city"
        else:
            confidence, match_level = "low", "city_broad"
    else:
        return {
            "listing_id": listing_id,
            "estimated_rent": None,
            "avg_rent_per_m2": None,
            "sample_count": 0,
            "confidence": "none",
            "match_level": "none",
            "rental_yield": None,
        }

    inv_two_sigma_sq = 0.5 / (ESTIMATE_AREA_SIGMA * ESTIMATE_AREA_SIGMA)
    vw: list[tuple[float, float]] = []
    for comp in pool:
        loc_w = 1.0 if comp["neighborhood"] == neighborhood else ESTIMATE_OTHER_PARISH_WEIGHT
        log_ratio = math.log(target_area / comp["area"])
        area_w = math.exp(-inv_two_sigma_sq * log_ratio * log_ratio)
        w = loc_w * area_w * comp["recency_w"]
        adj_rent = comp["rent"] * ((target_area / comp["area"]) ** ESTIMATE_AREA_EXPONENT)
        vw.append((adj_rent, w))

    raw_est_rent = _weighted_median(vw)
    estimated_rent = round(raw_est_rent)
    avg_rpm = round(raw_est_rent / target_area, 2)

    return {
        "listing_id": listing_id,
        "estimated_rent": estimated_rent,
        "avg_rent_per_m2": avg_rpm,
        "sample_count": len(pool),
        "confidence": confidence,
        "match_level": match_level,
        "rental_yield": round(estimated_rent * 12 / price, 4) if price else None,
    }


def _query_estimates(db: Session, where_clause: str, extra_params: dict) -> list[dict]:
    inputs = db.execute(
        text(
            f"""
            SELECT id, typology, neighborhood, city, area, price
            FROM listings
            WHERE area IS NOT NULL AND area > 0 AND typology IS NOT NULL
              {where_clause}
            """
        ),
        extra_params,
    ).fetchall()

    if not inputs:
        return []

    cities = {r.city for r in inputs if r.city}
    by_nt, by_ct = _load_comparable_pools(db, cities=cities if cities else None)

    estimates: list[dict] = []
    for r in inputs:
        est = _estimate_one(r.id, r.typology, r.neighborhood, r.city, r.area, r.price, by_nt, by_ct)
        if est is not None:
            estimates.append(est)
    return estimates


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
    """Run the size-curved weighted-median estimator for a single listing ID."""
    estimates = _query_estimates(db, "AND id = :id", {"id": listing_id})
    return estimates[0] if estimates else None


def compute_and_upsert_rental_estimates(db: Session, listing_ids: list[str]) -> int:
    """Compute and upsert rental estimates for *listing_ids*."""
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
