"""Pipeline step for refreshing rental estimates and gross yields."""

from __future__ import annotations

import logging
from typing import Optional

from yieldhunter.db.repository import refresh_rental_estimates
from yieldhunter.db.session import session_scope
from yieldhunter.pipeline.stats import city_slug, write_stats_file

logger = logging.getLogger(__name__)


def run_refresh_estimates(city: Optional[str] = None) -> dict:
    """Recompute rental estimates for active buy listings, optionally scoped to *city*."""
    label = city or "all cities"
    logger.info("Refreshing rental estimates (%s)…", label)
    with session_scope() as db:
        computed = refresh_rental_estimates(db, city=city)

    stats = {"type": "estimates", "city": city or "all", "computed": computed}
    write_stats_file(f"stats-estimates-{city_slug(city)}.json", stats)
    logger.info("Done — %d rental estimates computed/updated (%s)", computed, label)
    return stats
