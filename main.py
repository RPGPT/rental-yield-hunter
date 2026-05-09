import argparse
import logging

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


def run(source: str):
    scraper_cls = SCRAPERS.get(source)
    if not scraper_cls:
        logger.error("Unknown source: %s (available: %s)", source, ", ".join(SCRAPERS))
        return

    scraper = scraper_cls()

    logger.info("Scraping %s...", source)
    listings = scraper.run()

    db = Session()
    try:
        upsert_listings(db, listings)
        deactivate_missing(db, source, [listing["id"] for listing in listings])
        logger.info("Done — %d listings upserted from %s", len(listings), source)
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Rental Yield Hunter")
    ap.add_argument("--source", choices=list(SCRAPERS.keys()), default="imovirtual")
    run(source=ap.parse_args().source)
