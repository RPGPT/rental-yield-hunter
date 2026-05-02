import logging
import re
from datetime import datetime, timezone
from typing import Optional, List

from scraper.utils import has_tenants

logger = logging.getLogger(__name__)


def _parse_price(text: str) -> Optional[int]:
    """Parse price from Idealista format (e.g. '195.000 €' or '195000€')."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_area(text: str) -> Optional[int]:
    """Parse area from Idealista format (e.g. '85 m²' or '85m2')."""
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def parse_listing(item: dict) -> Optional[dict]:
    """
    Parse a single raw listing from the Idealista HTML scraper.

    Raw item fields (from fetcher):
    - id, title, price_text, area_text, rooms_text, description, url
    """
    try:
        listing_id = item.get("id", "")
        if not listing_id:
            return None

        title = item.get("title", "")
        price = _parse_price(item.get("price_text", ""))
        if price is None:
            return None  # Skip if no price

        area = _parse_area(item.get("area_text", ""))

        # Location: extract from title (Idealista titles often include location)
        location = "Porto"  # Default — fetcher targets Porto

        url = item.get("url", "")

        # Tenant detection from title + description
        description = item.get("description", "")
        searchable = f"{title} {description}".strip()

        return {
            "id": listing_id,
            "title": title,
            "price": price,
            "area": area,
            "location": location,
            "url": url,
            "has_tenants": has_tenants(searchable),
            "last_seen": datetime.now(timezone.utc),
        }
    except Exception as e:
        logger.debug("Failed to parse listing: %s", e)
        return None


def parse(api_responses: list) -> List[dict]:
    """
    Parse all Idealista fetcher responses and return ONLY listings
    with tenants (arrendada com inquilinos).
    """
    total_parsed = 0
    listings = []

    for response_data in api_responses:
        items = response_data.get("items", [])
        for item in items:
            listing = parse_listing(item)
            if not listing:
                continue

            total_parsed += 1

            # Only keep listings with tenants
            if not listing["has_tenants"]:
                continue

            listings.append(listing)

    logger.info(
        "Scanned %d Idealista listings → %d with tenants",
        total_parsed, len(listings),
    )

    for t in listings:
        logger.info(
            "  🏠 %s | %d€ | %s | %s",
            t["title"][:50], t["price"], t["location"], t["url"],
        )

    return listings
