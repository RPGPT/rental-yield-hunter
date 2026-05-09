import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import SUPPORTED_CITIES
from db.client import Session
from db.repository import deactivate_missing, upsert_listings
from scraper.imovirtual import ImovirtualScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

SCRAPERS = {
    "imovirtual": ImovirtualScraper,
}


def scrape_city(source: str, city: str) -> None:
    scraper_cls = SCRAPERS.get(source)
    if not scraper_cls:
        raise ValueError(f"Unknown source: {source!r} (available: {', '.join(SCRAPERS)})")

    logger.info("Scraping %s — %s...", source, city)
    scraper = scraper_cls(city)
    listings = scraper.run()

    db = Session()
    try:
        upsert_listings(db, listings)
        # Pass city so deactivation is scoped only to this city's rows —
        # required for correctness whether running sequentially or in parallel.
        active_ids = [listing["id"] for listing in listings]
        deactivate_missing(db, source, active_ids, city=city)
        logger.info("Done — %d listings upserted from %s / %s", len(listings), source, city)
    finally:
        db.close()


def scrape_all(source: str, cities: list[str], parallel: bool = False) -> None:
    if not parallel or len(cities) == 1:
        for city in cities:
            scrape_city(source, city)
        return

    # Each city gets its own DB session (SQLAlchemy sessions are not thread-safe).
    # The connection pool handles the underlying connections automatically.
    with ThreadPoolExecutor(max_workers=len(cities)) as executor:
        futures = {executor.submit(scrape_city, source, city): city for city in cities}
        for future in as_completed(futures):
            city = futures[future]
            try:
                future.result()
            except Exception:
                logger.exception("Error scraping %s / %s", source, city)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Rental Yield Hunter")
    ap.add_argument("--source", choices=list(SCRAPERS.keys()), default="imovirtual")
    ap.add_argument(
        "--city",
        choices=SUPPORTED_CITIES,
        default=None,
        help="City to scrape. Omit to scrape all supported cities.",
    )
    ap.add_argument(
        "--parallel",
        action="store_true",
        default=False,
        help="Scrape all cities in parallel using a thread pool.",
    )
    args = ap.parse_args()

    cities_to_scrape = [args.city] if args.city else SUPPORTED_CITIES
    scrape_all(source=args.source, cities=cities_to_scrape, parallel=args.parallel)
