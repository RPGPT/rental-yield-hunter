import argparse
import json
import logging
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from config import REQUEST_DELAY, SUPPORTED_CITIES
from db.client import Session
from db.repository import (
    deactivate_missing,
    deactivate_missing_rentals,
    get_rented_listings_for_extraction,
    refresh_rental_estimates,
    upsert_contract_details,
    upsert_listings,
    upsert_rental_listings,
)
from scraper.contract_extractor import extract_rent_and_expiry
from scraper.imovirtual import ImovirtualBuyScraper, ImovirtualRentalScraper
from scraper.imovirtual.fetcher import _fetch_detail, _get_build_id

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


def run_refresh_estimates(city: Optional[str] = None) -> dict:
    """Recompute rental estimates for active buy listings, optionally scoped to *city*."""
    label = city or "all cities"
    logger.info("Refreshing rental estimates (%s)…", label)
    db = Session()
    try:
        computed = refresh_rental_estimates(db, city=city)
    finally:
        db.close()

    slug = city.replace(" ", "-") if city else "all"
    stats = {"type": "estimates", "city": city or "all", "computed": computed}
    pathlib.Path(f"stats-estimates-{slug}.json").write_text(json.dumps(stats))
    logger.info("Done — %d rental estimates computed/updated (%s)", computed, label)
    return stats


def run_extract_contracts(city: Optional[str] = None) -> dict:
    """Fetch full descriptions for rented listings and extract contract details."""
    from curl_cffi import requests as curl_requests

    from scraper.imovirtual.constants import BASE_URL, BUY_CITY_PATHS

    label = city or "all cities"
    logger.info("Extracting contract details (%s)…", label)

    db = Session()
    try:
        listings = get_rented_listings_for_extraction(db, city=city)
    finally:
        db.close()

    if not listings:
        logger.info("No rented listings to process (%s)", label)
        stats = {"type": "contracts", "city": city or "all", "processed": 0, "with_rent": 0, "with_expiry": 0}
        slug = city.replace(" ", "-") if city else "all"
        pathlib.Path(f"stats-contracts-{slug}.json").write_text(json.dumps(stats))
        return stats

    logger.info("Found %d rented listings to process (%s)", len(listings), label)

    # Group listings by city so we get one buildId per city
    session = curl_requests.Session(impersonate="chrome")
    details_to_upsert = []
    with_rent = 0
    with_expiry = 0

    # We need a buildId — use the first city's path
    cities_needed = set()
    for listing in listings:
        # Determine city from URL path
        for c, (search_path, _) in BUY_CITY_PATHS.items():
            if city and c != city:
                continue
            cities_needed.add(c)

    build_ids = {}
    for c in cities_needed:
        if c in BUY_CITY_PATHS:
            search_path, _ = BUY_CITY_PATHS[c]
            bid = _get_build_id(session, BASE_URL + search_path)
            if bid:
                build_ids[c] = bid

    if not build_ids:
        logger.warning("Could not get any buildId — aborting contract extraction")
        stats = {"type": "contracts", "city": city or "all", "processed": 0, "with_rent": 0, "with_expiry": 0}
        slug = city.replace(" ", "-") if city else "all"
        pathlib.Path(f"stats-contracts-{slug}.json").write_text(json.dumps(stats))
        return stats

    # Use any available buildId (they're usually the same across cities)
    default_build_id = next(iter(build_ids.values()))

    for i, listing in enumerate(listings):
        url = listing.get("url", "")
        if not url:
            continue

        detail = _fetch_detail(session, url, default_build_id)
        if detail:
            desc = detail.get("description") or ""
            full_desc = detail.get("full_description") or ""
            combined = f"{listing.get('title', '')} {desc} {full_desc}".strip()
        else:
            combined = f"{listing.get('title', '')} {listing.get('description', '')}".strip()

        if not combined:
            continue

        result = extract_rent_and_expiry(combined)

        if result["current_rent_amount"] is not None or result["contract_expiry_date"] is not None:
            details_to_upsert.append(
                {
                    "listing_id": listing["id"],
                    "current_rent": result["current_rent_amount"],
                    "contract_expiry_date": result["contract_expiry_date"],
                    "raw_rent_text": result["raw_rent_text"],
                    "raw_expiry_text": result["raw_expiry_text"],
                    "confidence": result["confidence"],
                }
            )
            if result["current_rent_amount"] is not None:
                with_rent += 1
            if result["contract_expiry_date"] is not None:
                with_expiry += 1

        if (i + 1) % 20 == 0:
            logger.info("Processed %d/%d listings", i + 1, len(listings))

        time.sleep(REQUEST_DELAY)

    # Upsert in batches
    if details_to_upsert:
        db = Session()
        try:
            upsert_contract_details(db, details_to_upsert)
        finally:
            db.close()

    slug = city.replace(" ", "-") if city else "all"
    stats = {
        "type": "contracts",
        "city": city or "all",
        "processed": len(listings),
        "with_rent": with_rent,
        "with_expiry": with_expiry,
        "extracted": len(details_to_upsert),
    }
    pathlib.Path(f"stats-contracts-{slug}.json").write_text(json.dumps(stats))
    logger.info(
        "Done — %d/%d listings yielded contract data (%d rent, %d expiry) (%s)",
        len(details_to_upsert),
        len(listings),
        with_rent,
        with_expiry,
        label,
    )
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
        choices=["buy", "rent", "estimates", "contracts"],
        default="buy",
        help="buy/rent scraping, rent estimates refresh, or contract detail extraction.",
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
        run_refresh_estimates(city=args.city)
    elif args.listing_type == "contracts":
        run_extract_contracts(city=args.city)
    else:
        cities_to_scrape = [args.city] if args.city else SUPPORTED_CITIES
        scrape_all(
            source=args.source,
            cities=cities_to_scrape,
            listing_type=args.listing_type,
            parallel=args.parallel,
        )
