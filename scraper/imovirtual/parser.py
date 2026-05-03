import logging
import re
from datetime import datetime, timezone
from typing import Optional

from config import MAX_PRICE, MIN_PRICE
from scraper.imovirtual.constants import BASE_URL, SOURCE, ESTATE_MAP, ROOMS_MAP
from scraper.utils import is_rented

logger = logging.getLogger(__name__)


def build_url(href: str) -> Optional[str]:
    if not href:
        return None
    href = href.replace("[lang]", "pt").replace("/ad/", "/anuncio/")
    href = re.sub(r"/hpr/", "/", href)
    if href.startswith("http"):
        return href
    return BASE_URL + href.lstrip("/")


def extract_id(item: dict, url: str) -> Optional[str]:
    raw_id = item.get("id")
    if raw_id:
        return str(raw_id)
    match = re.search(r"ID([a-zA-Z0-9]+)$", url.rstrip("/"))
    return match.group(1) if match else None


def build_location(location_obj: dict) -> tuple:
    addr = location_obj.get("address", {})
    street = addr.get("street", {}).get("name", "")
    city = addr.get("city", {}).get("name", "")
    province = addr.get("province", {}).get("name", "")
    raw = ", ".join(p for p in [street, city, province] if p)
    return raw, city or None


def parse_listing(item: dict) -> Optional[dict]:
    try:
        price_val = (item.get("totalPrice") or {}).get("value")
        if price_val is None:
            return None

        price = int(price_val)
        if price > MAX_PRICE or price < MIN_PRICE:
            return None

        url = build_url(item.get("href", ""))
        if not url:
            return None

        listing_id = extract_id(item, url)
        if not listing_id:
            return None

        title = item.get("title", "")
        description = item.get("shortDescription", "")
        area = item.get("areaInSquareMeters")
        ppm2 = (item.get("pricePerSquareMeter") or {}).get("value")
        location, city = build_location(item.get("location", {}))
        tags = item.get("tags") or []
        features = item.get("features") or []

        now = datetime.now(timezone.utc)

        return {
            "id": listing_id,
            "source": SOURCE,
            "url": url,
            "title": title,
            "description": description,
            "price": price,
            "area": int(area) if area is not None else None,
            "price_per_m2": float(ppm2) if ppm2 is not None else None,
            "location": location,
            "city": city,
            "property_type": ESTATE_MAP.get(item.get("estate")),
            "typology": ROOMS_MAP.get(item.get("roomsNumber")),
            "floor": str(item["floorNumber"]) if item.get("floorNumber") is not None else None,
            "has_garage": "PARKING_SPOT" in tags or "garage" in " ".join(features).lower(),
            "is_rented": is_rented(f"{title} {description}"),
            "lifetime_rent": False,
            "active": True,
            "inactive_since": None,
            "last_seen": now,
            "updated_at": now,
            "_raw_json": item,
        }
    except Exception:
        logger.debug("Failed to parse listing", exc_info=True)
        return None


def parse(responses: list[dict]) -> list[dict]:
    seen = set()
    listings = []

    for response in responses:
        for item in response.get("items", []):
            listing = parse_listing(item)
            if not listing or listing["id"] in seen:
                continue
            seen.add(listing["id"])
            listings.append(listing)

    rented = sum(1 for l in listings if l["is_rented"])
    logger.info("Parsed %d unique listings — %d flagged as rented", len(listings), rented)

    return listings
