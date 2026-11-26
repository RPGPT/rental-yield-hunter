"""Imovirtual Next.js JSON -> normalized listing dict parser."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from yieldhunter.analysis.rented import is_rented
from yieldhunter.analysis.typology import rooms_word_to_typology as rooms_to_typology
from yieldhunter.analysis.typology import typology_from_title
from yieldhunter.config import MAX_PRICE, MIN_PRICE, PARISH_CITIES
from yieldhunter.sources.imovirtual.constants import BASE_URL, ESTATE_MAP, SOURCE

logger = logging.getLogger(__name__)

_ID_SUFFIX_RE = re.compile(r"ID([a-zA-Z0-9]+)$")
_HPR_SEGMENT_RE = re.compile(r"/hpr/")


def build_url(href: str) -> Optional[str]:
    if not href:
        return None
    href = href.replace("[lang]", "pt").replace("/ad/", "/anuncio/")
    href = _HPR_SEGMENT_RE.sub("/", href)
    if href.startswith("http"):
        return href
    return BASE_URL + href.lstrip("/")


def extract_id(item: dict, url: str) -> Optional[str]:
    raw_id = item.get("id")
    if raw_id:
        return str(raw_id)
    match = _ID_SUFFIX_RE.search(url.rstrip("/"))
    return match.group(1) if match else None


def build_location(location_obj: dict) -> tuple[str, Optional[str], Optional[str]]:
    addr = location_obj.get("address") or {}
    street = (addr.get("street") or {}).get("name", "")

    rev_locations = (location_obj.get("reverseGeocoding") or {}).get("locations") or []
    rev = {loc["locationLevel"]: loc["name"] for loc in rev_locations}

    neighborhood = rev.get("parish") or (addr.get("city") or {}).get("name") or None
    city = rev.get("council") or (addr.get("province") or {}).get("name") or None

    raw = ", ".join(p for p in [street, neighborhood, city] if p)
    return raw, neighborhood or None, city or None


def parse_listing(
    item: dict,
    target_city: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
) -> Optional[dict]:
    resolved_min = min_price if min_price is not None else MIN_PRICE
    resolved_max = max_price if max_price is not None else MAX_PRICE

    try:
        price_val = (item.get("totalPrice") or {}).get("value")
        if price_val is None:
            return None

        price = int(price_val)
        if price > resolved_max or price < resolved_min:
            return None

        url = build_url(item.get("href", ""))
        if not url:
            return None

        listing_id = extract_id(item, url)
        if not listing_id:
            return None

        title = item.get("title", "")
        description = item.get("shortDescription", "") or ""
        area = item.get("areaInSquareMeters")
        ppm2 = (item.get("pricePerSquareMeter") or {}).get("value")
        location, neighborhood, city = build_location(item.get("location", {}))
        if target_city in PARISH_CITIES:
            if neighborhood != target_city:
                return None
            city = target_city
        elif target_city is not None and city and city != target_city:
            return None

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
            "rent_price_per_m2": round(price / int(area), 2) if area else (float(ppm2) if ppm2 is not None else None),
            "location": location,
            "neighborhood": neighborhood,
            "city": city,
            "property_type": ESTATE_MAP.get(item.get("estate")),
            "typology": rooms_to_typology(item.get("roomsNumber")) or typology_from_title(title),
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


def parse(
    responses: list[dict],
    target_city: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
) -> list[dict]:
    seen: set[str] = set()
    listings: list[dict] = []

    for response in responses:
        for item in response.get("items", []):
            listing = parse_listing(item, target_city, min_price=min_price, max_price=max_price)
            if not listing or listing["id"] in seen:
                continue
            seen.add(listing["id"])
            listings.append(listing)

    rented = sum(1 for listing in listings if listing["is_rented"])
    logger.info("Parsed %d unique listings — %d flagged as rented", len(listings), rented)
    return listings


__all__ = [
    "build_location",
    "build_url",
    "extract_id",
    "parse",
    "parse_listing",
    "rooms_to_typology",
    "typology_from_title",
]
