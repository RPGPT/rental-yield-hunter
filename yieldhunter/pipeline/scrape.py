"""Scrape orchestration for single cities and parallel multi-city runs."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from yieldhunter.db.repository import (
    deactivate_missing,
    deactivate_missing_rentals,
    get_rented_listing_ids,
    upsert_listings,
    upsert_rental_listings,
)
from yieldhunter.db.session import session_scope
from yieldhunter.pipeline.stats import city_slug, write_stats_file
from yieldhunter.sources.imovirtual import ImovirtualBuyScraper
from yieldhunter.sources.registry import create_scraper

logger = logging.getLogger(__name__)


def scrape_city(source: str, city: str, listing_type: str = "buy") -> dict:
    scraper = create_scraper(source, listing_type, city)
    logger.info("Scraping %s — %s [%s]...", source, city, listing_type)

    if isinstance(scraper, ImovirtualBuyScraper):
        with session_scope() as db:
            scraper.known_rented_ids = get_rented_listing_ids(db, city, source)

    result = scraper.run_checked()
    listings = result.listings
    active_ids = [listing["id"] for listing in listings]

    with session_scope() as db:
        if listing_type == "rent":
            n_price_changes = upsert_rental_listings(db, listings)
            if result.complete:
                deactivate_missing_rentals(db, source, active_ids, city=city)
            else:
                logger.warning(
                    "Skipping rental deactivation for %s / %s — scrape was incomplete",
                    source,
                    city,
                )
        else:
            n_price_changes = upsert_listings(db, listings)
            if result.complete:
                deactivate_missing(db, source, active_ids, city=city)
            else:
                logger.warning(
                    "Skipping buy deactivation for %s / %s — scrape was incomplete",
                    source,
                    city,
                )

    stats: dict = {
        "city": city,
        "source": source,
        "type": listing_type,
        "fetched": len(listings),
        "price_changes": n_price_changes,
    }
    if listing_type == "buy":
        stats["rented"] = sum(1 for listing in listings if listing.get("is_rented"))
        logger.info(
            "Done — %d fetched, %d rented, %d price changes (%s / %s / %s)",
            stats["fetched"],
            stats["rented"],
            stats["price_changes"],
            source,
            city,
            listing_type,
        )
    else:
        logger.info(
            "Done — %d fetched, %d price changes (%s / %s / %s)",
            stats["fetched"],
            stats["price_changes"],
            source,
            city,
            listing_type,
        )

    write_stats_file(f"stats-{listing_type}-{source}-{city_slug(city)}.json", stats)
    return stats


def scrape_all(source: str, cities: list[str], listing_type: str = "buy", parallel: bool = False) -> None:
    if not parallel or len(cities) == 1:
        for city in cities:
            scrape_city(source, city, listing_type)
        return

    with ThreadPoolExecutor(max_workers=len(cities)) as executor:
        futures = {executor.submit(scrape_city, source, city, listing_type): city for city in cities}
        for future in as_completed(futures):
            city = futures[future]
            try:
                future.result()
            except Exception:
                logger.exception("Error scraping %s / %s / %s", source, city, listing_type)
