"""ERA.pt JSON -> normalized listing dict parser."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from yieldhunter.analysis.rented import is_rented
from yieldhunter.analysis.typology import rooms_int_to_typology as _typology_from_rooms
from yieldhunter.analysis.typology import typology_from_title as _typology_from_title
from yieldhunter.config import PARISH_CITIES
from yieldhunter.sources.era.constants import PROPERTY_TYPE_MAP, SEARCH_SCOPED_CITIES, SOURCE

logger = logging.getLogger(__name__)

_NUMERIC_PREFIX_RE = re.compile(r"^\d+-\s*")
_NON_NUMERIC_PRICES = {"sob consulta", "preço sob consulta", "price on request"}


def _parse_price(value_str: Optional[str]) -> Optional[int]:
    if not value_str:
        return None
    s = value_str.replace("€", "").replace("\xa0", "").strip()
    if not s or s.lower() in _NON_NUMERIC_PRICES:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(".", "")
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _parse_location(localization: str) -> tuple[str, Optional[str], Optional[str]]:
    if not localization:
        return "", None, None
    idx = localization.rfind(",")
    if idx != -1:
        neighborhood = localization[:idx].strip()
        city = localization[idx + 1 :].strip()
        return localization, neighborhood or None, city or None
    return localization, None, localization


def parse_listing(
    item: dict,
    target_city: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    listing_type: str = "buy",
) -> Optional[dict]:
    try:
        is_rent = listing_type == "rent"
        price_key = "RentPrice" if is_rent else "SellPrice"
        price = _parse_price((item.get(price_key) or {}).get("Value"))

        if price is None:
            return None
        if min_price is not None and price < min_price:
            return None
        if max_price is not None and price > max_price:
            return None

        if not item.get("IsOnline", True):
            return None
        if (item.get("BusinessStatus") or {}).get("Id") != 1:
            return None

        url = item.get("DetailUrl") or ""
        if not url:
            return None

        reference = item.get("Reference")
        if not reference:
            return None
        listing_id = f"era-{reference}"

        title = item.get("Title") or ""
        localization = item.get("Localization") or ""
        location, neighborhood, city = _parse_location(localization)

        if target_city in SEARCH_SCOPED_CITIES:
            parts = [p.strip() for p in localization.split(",") if p.strip()]
            if target_city in PARISH_CITIES:
                if target_city not in parts:
                    return None
                neighborhood = target_city
            else:
                neighborhood = _NUMERIC_PREFIX_RE.sub("", parts[0]) if parts else None
            city = target_city
        elif target_city is not None and city and city != target_city:
            return None

        area = item.get("ListingArea")
        floor_val = item.get("Floor")
        rooms = item.get("Rooms")
        parking = item.get("Parking")
        property_type_str = item.get("PropertyType") or ""

        price_per_m2 = round(price / int(area), 2) if area else None
        now = datetime.now(timezone.utc)

        return {
            "id": listing_id,
            "source": SOURCE,
            "url": url,
            "title": title,
            "description": "",
            "price": price,
            "area": int(area) if area is not None else None,
            "price_per_m2": price_per_m2,
            "rent_price_per_m2": price_per_m2 if is_rent else None,
            "location": location,
            "neighborhood": neighborhood,
            "city": city,
            "property_type": PROPERTY_TYPE_MAP.get(property_type_str, property_type_str.lower() or None),
            "typology": _typology_from_rooms(rooms) or _typology_from_title(title),
            "floor": str(floor_val) if floor_val is not None else None,
            "has_garage": bool(parking) and int(parking) > 0 if parking is not None else False,
            "is_rented": is_rented(title) if not is_rent else False,
            "lifetime_rent": False,
            "active": True,
            "inactive_since": None,
            "last_seen": now,
            "updated_at": now,
            "_raw_json": item,
        }
    except Exception:
        logger.debug("Failed to parse ERA listing", exc_info=True)
        return None


def parse(
    responses: list[dict],
    target_city: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    listing_type: str = "buy",
) -> list[dict]:
    seen: set[str] = set()
    listings: list[dict] = []

    for response in responses:
        for item in response.get("PropertyList", []):
            listing = parse_listing(item, target_city, min_price, max_price, listing_type)
            if not listing or listing["id"] in seen:
                continue
            seen.add(listing["id"])
            listings.append(listing)

    rented = sum(1 for item in listings if item.get("is_rented"))
    if listing_type == "buy":
        logger.info("ERA parsed %d unique listings — %d flagged as rented", len(listings), rented)
    else:
        logger.info("ERA parsed %d unique rental listings", len(listings))

    return listings
