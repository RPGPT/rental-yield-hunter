"""Persistence for cross-source deduplication & price-arbitrage clusters (``listing_clusters``)."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from yieldhunter.analysis.clustering import build_listing_clusters
from yieldhunter.db.models import ListingCluster
from yieldhunter.db.repository.common import chunks

logger = logging.getLogger(__name__)


def refresh_listing_clusters(db: Session, city: Optional[str] = None) -> dict:
    """Cluster active, non-deleted buy listings and upsert ``listing_clusters``."""
    label = city or "all cities"
    city_clause = "AND city = :city" if city else ""
    params = {"city": city} if city else {}

    rows = (
        db.execute(
            text(
                f"""
            SELECT id, source, city, neighborhood, typology, area, price,
                   floor, has_garage, location, title, description
            FROM listings
            WHERE active = true AND is_deleted = false AND price IS NOT NULL AND price > 0
              {city_clause}
            """
            ),
            params,
        )
        .mappings()
        .all()
    )

    if not rows:
        logger.info("No eligible buy listings for clustering (%s)", label)
        return {"listings": 0, "multi_agency_clusters": 0, "duplicate_listings": 0}

    cluster_rows = build_listing_clusters([dict(r) for r in rows])

    # Remove stale cluster rows for deactivated/deleted listings in scope
    if city:
        db.execute(
            text(
                """
                DELETE FROM listing_clusters lc
                USING listings l
                WHERE lc.listing_id = l.id AND l.city = :city
                  AND (l.active = false OR l.is_deleted = true)
                """
            ),
            {"city": city},
        )
    else:
        db.execute(
            text(
                """
                DELETE FROM listing_clusters lc
                USING listings l
                WHERE lc.listing_id = l.id AND (l.active = false OR l.is_deleted = true)
                """
            )
        )

    for chunk in chunks(cluster_rows):
        stmt = insert(ListingCluster).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["listing_id"],
            set_={
                "cluster_id": stmt.excluded.cluster_id,
                "cluster_size": stmt.excluded.cluster_size,
                "cluster_min_price": stmt.excluded.cluster_min_price,
                "cluster_max_price": stmt.excluded.cluster_max_price,
                "price_spread": stmt.excluded.price_spread,
                "price_spread_pct": stmt.excluded.price_spread_pct,
                "is_cheapest": stmt.excluded.is_cheapest,
                "sources": stmt.excluded.sources,
                "computed_at": text("NOW()"),
            },
        )
        db.execute(stmt)

    db.commit()

    multi_ids = {r["cluster_id"] for r in cluster_rows if r["cluster_size"] > 1}
    dup_rows = sum(1 for r in cluster_rows if r["cluster_size"] > 1)
    logger.info(
        "Clustered %d buy listings into %d multi-agency clusters (%d listings in multi-agency groups) (%s)",
        len(cluster_rows),
        len(multi_ids),
        dup_rows,
        label,
    )
    return {
        "listings": len(cluster_rows),
        "multi_agency_clusters": len(multi_ids),
        "duplicate_listings": dup_rows,
    }
