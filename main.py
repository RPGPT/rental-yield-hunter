import argparse
import logging

from db.client import Session
from db.repository import deactivate_missing, upsert_listings
from scraper.imovirtual import ImovirtualScraper
from scraper.imovirtual.constants import DEFAULT_CITIES, SUPPORTED_CITIES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

SCRAPERS = {
    "imovirtual": ImovirtualScraper,
}


def run(source: str, city: str):
    scraper_cls = SCRAPERS.get(source)
    if not scraper_cls:
        logger.error("Unknown source: %s (available: %s)", source, ", ".join(SCRAPERS))
        return

    scraper = scraper_cls(city)
    council_name = SUPPORTED_CITIES[city][1]

    logger.info("Scraping %s — %s...", source, city)
    listings = scraper.run()

    db = Session()
    try:
        upsert_listings(db, listings)
        deactivate_missing(db, source, [listing["id"] for listing in listings], city=council_name)
        logger.info("Done — %d listings upserted from %s (%s)", len(listings), source, city)
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Rental Yield Hunter")
    ap.add_argument("--source", choices=list(SCRAPERS.keys()), default="imovirtual")
    ap.add_argument(
        "--city",
        choices=list(SUPPORTED_CITIES.keys()),
        default=None,
        help="City to scrape. Omit to scrape all default cities: %(default)s",
    )
    args = ap.parse_args()

    cities = [args.city] if args.city else DEFAULT_CITIES
    for city in cities:
        run(source=args.source, city=city)
