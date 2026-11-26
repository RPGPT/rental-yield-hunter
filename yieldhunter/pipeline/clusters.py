"""Pipeline step for cross-source deduplication and multi-agency price arbitrage."""

from __future__ import annotations

import logging
from typing import Optional

from yieldhunter.db.repository.clusters import refresh_listing_clusters
from yieldhunter.db.session import session_scope
from yieldhunter.pipeline.stats import city_slug, write_stats_file

logger = logging.getLogger(__name__)


def run_refresh_clusters(city: Optional[str] = None) -> dict:
    label = city or "all cities"
    logger.info("Refreshing listing clusters (%s)…", label)
    with session_scope() as db:
        counts = refresh_listing_clusters(db, city=city)

    stats = {
        "type": "clusters",
        "city": city or "all",
        **counts,
    }
    write_stats_file(f"stats-clusters-{city_slug(city)}.json", stats)
    return stats
