import argparse
import json
import logging
import pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import SUPPORTED_CITIES
from db.client import Session
from db.repository import (
    deactivate_missing,
    deactivate_missing_rentals,
    refresh_rental_estimates,
    upsert_listings,
    upsert_rental_listings,
)
from scraper.imovirtual import ImovirtualBuyScraper, ImovirtualRentalScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

SCRAPERS = {
    "imovirtual": {
        "buy": ImovirtualBuyScraper,
        "rent": ImovirtualRentalScraper,
    },
}


def scrape_city(source: str, city: str, listing_type: str = "buy") -> dict:
    source_scrapers = SCRAPERS.get(source)
    if not source_scrapers:
        raise ValueError(f"Unknown source: {source!r} (available: {', '.join(SCRAPERS)})")

    scraper_cls = source_scrapers.get(listing_type)
    if not scraper_cls:
        raise ValueError(f"Unknown listing type: {listing_type!r} (available: buy, rent)")

    logger.info("Scraping %s — %s [%s]...", source, city, listing_type)
    scraper = scraper_cls(city)
    listings = scraper.run()

    db = Session()
    try:
        if listing_type == "rent":
            n_price_changes = upsert_rental_listings(db, listings)
            active_ids = [listing["id"] for listing in listings]
            deactivate_missing_rentals(db, source, active_ids, city=city)
        else:
            n_price_changes = upsert_listings(db, listings)
            active_ids = [listing["id"] for listing in listings]
            deactivate_missing(db, source, active_ids, city=city)
    finally:
        db.close()

    stats = {
        "city": city,
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

    slug = city.replace(" ", "-")
    pathlib.Path(f"stats-{listing_type}-{slug}.json").write_text(json.dumps(stats))

    return stats


def run_refresh_estimates() -> dict:
    """Recompute rental estimates for all active buy listings in the DB."""
    logger.info("Refreshing rental estimates for all active listings…")
    db = Session()
    try:
        computed = refresh_rental_estimates(db)
    finally:
        db.close()

    stats = {"type": "estimates", "computed": computed}
    pathlib.Path("stats-estimates.json").write_text(json.dumps(stats))
    logger.info("Done — %d rental estimates computed/updated", computed)
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Rental Yield Hunter")
    ap.add_argument("--source", choices=list(SCRAPERS.keys()), default="imovirtual")
    ap.add_argument(
        "--type",
        dest="listing_type",
        choices=["buy", "rent", "estimates"],
        default="buy",
        help="Whether to scrape buy/rental listings or refresh rent estimates (DB-wide).",
    )
    ap.add_argument(
        "--city",
        choices=SUPPORTED_CITIES,
        default=None,
        help="City to scrape. Omit to scrape all supported cities. Ignored for --type estimates.",
    )
    ap.add_argument(
        "--parallel",
        action="store_true",
        default=False,
        help="Scrape all cities in parallel using a thread pool.",
    )
    args = ap.parse_args()

    if args.listing_type == "estimates":
        run_refresh_estimates()
    else:
        cities_to_scrape = [args.city] if args.city else SUPPORTED_CITIES
        scrape_all(
            source=args.source,
            cities=cities_to_scrape,
            listing_type=args.listing_type,
            parallel=args.parallel,
        )
