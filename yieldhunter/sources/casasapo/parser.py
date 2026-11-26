"""Casa Sapo HTML + embedded ``schema.org/RealEstateListing`` JSON-LD parser.

Casa Sapo renders every search result card as ``<div id="property_<UUID>" class="property">``
containing both structured ``application/ld+json`` metadata and the full untruncated
``.property-description`` text, so ``is_rented``, ``lifetime_rent``, and ``fullDescription``
are extracted directly from search pages without N×detail HTTP requests.
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from yieldhunter.analysis.rented import is_lifetime_rent, is_rented
from yieldhunter.analysis.typology import typology_from_title
from yieldhunter.config import PARISH_CITIES
from yieldhunter.sources.casasapo.constants import BASE_URL, SOURCE

logger = logging.getLogger(__name__)

_CARD_SPLIT_RE = re.compile(r'<div id="property_([0-9a-fA-F-]+)" class="property">')
_LD_JSON_RE = re.compile(
    r'<script\s+type=["\']application/ld(?:&#x2B;|\+)json["\']\s*>\s*(\{.*?\})\s*</script>',
    re.DOTALL | re.IGNORECASE,
)
_HREF_INFO_RE = re.compile(r'<a\s+href="([^"]+)"[^>]*class="property-info"', re.IGNORECASE)
_HREF_FALLBACK_RE = re.compile(r'<a\s+href="(/[^"]+\.html)"', re.IGNORECASE)
_PROP_TYPE_RE = re.compile(r'<div class="property-type">(.*?)</div>', re.DOTALL | re.IGNORECASE)
_PROP_LOC_RE = re.compile(r'<div class="property-location">(.*?)</div>', re.DOTALL | re.IGNORECASE)
_PROP_FEAT_RE = re.compile(r'<div class="property-features">(.*?)</div>\s*<div class="property-price">', re.DOTALL)
_PROP_PRICE_RE = re.compile(r'<div class="property-price-value">(.*?)</div>', re.DOTALL | re.IGNORECASE)
_PROP_DESC_RE = re.compile(r'<div class="property-description">(.*?)</div>', re.DOTALL | re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_AREA_TEXT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m(?:²|2)\b", re.IGNORECASE)
_FLOOR_TEXT_RE = re.compile(r"\b(\d+)\s*[º°]\s*andar\b|\b(r/c|rés[- ]do[- ]chão)\b", re.IGNORECASE)
_WS_RE = re.compile(r"[ \t]+")


def _clean_html_text(raw: str, preserve_newlines: bool = False) -> str:
    if not raw:
        return ""
    s = _BR_RE.sub("\n" if preserve_newlines else " ", raw)
    s = _TAG_RE.sub(" ", s)
    s = html_lib.unescape(s)
    if preserve_newlines:
        lines = [_WS_RE.sub(" ", ln).strip() for ln in s.splitlines()]
        return "\n".join(ln for ln in lines if ln)
    return re.sub(r"\s+", " ", s).strip()


def parse_price(raw_price) -> Optional[int]:
    if raw_price is None:
        return None
    if isinstance(raw_price, list):
        raw_price = raw_price[0] if raw_price else None
    if raw_price is None:
        return None
    if isinstance(raw_price, (int, float)):
        return int(raw_price)
    s = html_lib.unescape(str(raw_price))
    # Strip "/mês", currency symbols, spaces
    s = re.split(r"/", s)[0]
    s = s.replace("€", "").replace("\xa0", "").replace(" ", "").strip()
    if not s or any(w in s.lower() for w in ("consulta", "request", "sob")):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(".", "")
    digits = re.match(r"^\d+(?:\.\d+)?$", s)
    if not digits:
        return None
    return int(float(s))


def _parse_location(loc_text: str, ld_address: dict) -> tuple[str, Optional[str], Optional[str]]:
    cleaned = re.sub(r",?\s*Distrito\s+d[eo]\s+Porto\s*$", "", loc_text, flags=re.IGNORECASE).strip(" ,")
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if len(parts) >= 2:
        city = parts[-1]
        neighborhood = parts[-2]
        return cleaned, neighborhood, city
    if len(parts) == 1:
        city = parts[0]
        return cleaned, city, city

    locality = (ld_address.get("addressLocality") or "").strip() or None
    region = (ld_address.get("addressRegion") or "").strip() or None
    if region and "distrito" in region.lower():
        region = None
    raw = ", ".join(p for p in [region, locality] if p)
    return raw, region or locality, locality


def _extract_floor(text: str) -> Optional[str]:
    m = _FLOOR_TEXT_RE.search(text)
    if not m:
        return None
    if m.group(1):
        return m.group(1)
    return "0"


def extract_cards(html: str) -> list[dict]:
    """Extract raw card dicts from a Casa Sapo search HTML page."""
    matches = list(_CARD_SPLIT_RE.finditer(html))
    cards: list[dict] = []

    for idx, match in enumerate(matches):
        uid = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(html), start + 25_000)
        chunk = html[start:end]

        ld_data: dict = {}
        ld_match = _LD_JSON_RE.search(chunk)
        if ld_match:
            try:
                parsed = json.loads(html_lib.unescape(ld_match.group(1)))
                if isinstance(parsed, dict):
                    ld_data = parsed
            except ValueError:
                pass

        href_m = _HREF_INFO_RE.search(chunk) or _HREF_FALLBACK_RE.search(chunk)
        href = html_lib.unescape(href_m.group(1)) if href_m else ""

        type_m = _PROP_TYPE_RE.search(chunk)
        loc_m = _PROP_LOC_RE.search(chunk)
        feat_m = _PROP_FEAT_RE.search(chunk)
        price_m = _PROP_PRICE_RE.search(chunk)
        desc_m = _PROP_DESC_RE.search(chunk)

        cards.append(
            {
                "uid": uid,
                "href": href,
                "type_text": _clean_html_text(type_m.group(1)) if type_m else "",
                "location_text": _clean_html_text(loc_m.group(1)) if loc_m else "",
                "features_text": _clean_html_text(feat_m.group(1)) if feat_m else "",
                "price_text": _clean_html_text(price_m.group(1)) if price_m else "",
                "description": _clean_html_text(desc_m.group(1), preserve_newlines=True) if desc_m else "",
                "ld": ld_data,
            }
        )

    return cards


def parse_card(
    card: dict,
    target_city: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    listing_type: str = "buy",
) -> Optional[dict]:
    try:
        is_rent = listing_type == "rent"
        ld = card.get("ld") or {}
        main = ld.get("mainEntity") or {}
        offers = ld.get("offers") or {}

        price = parse_price(offers.get("price")) or parse_price(card.get("price_text"))
        if price is None:
            return None
        if min_price is not None and price < min_price:
            return None
        if max_price is not None and price > max_price:
            return None

        uid = card.get("uid") or main.get("identifier")
        if not uid:
            return None
        listing_id = f"casasapo-{uid}"

        href = card.get("href") or ""
        if not href:
            return None
        url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"

        title = main.get("name") or card.get("type_text") or ""
        title = html_lib.unescape(title).strip()
        description = card.get("description") or _clean_html_text(main.get("description") or "")

        ld_addr = ((main.get("availableAtOrFrom") or {}).get("address")) or {}
        location, neighborhood, city = _parse_location(card.get("location_text") or "", ld_addr)

        if target_city in PARISH_CITIES:
            haystack = f"{location} {neighborhood or ''} {city or ''}".casefold()
            if target_city.casefold() not in haystack:
                return None
            neighborhood = target_city
            city = target_city
        elif target_city is not None and city and city.casefold() != target_city.casefold():
            return None

        area_val = (main.get("floorSize") or {}).get("value")
        if area_val is None:
            area_m = _AREA_TEXT_RE.search(card.get("features_text") or "")
            if area_m:
                area_val = float(area_m.group(1).replace(",", "."))
        area = int(round(float(area_val))) if area_val is not None and float(area_val) > 0 else None

        ppm2 = round(price / area, 2) if area else None
        features_lower = (card.get("features_text") or "").lower()
        combined_text = f"{title} {description}".strip()
        now = datetime.now(timezone.utc)

        return {
            "id": listing_id,
            "source": SOURCE,
            "url": url,
            "title": title,
            "description": description,
            "price": price,
            "area": area,
            "price_per_m2": ppm2,
            "rent_price_per_m2": ppm2 if is_rent else None,
            "location": location,
            "neighborhood": neighborhood,
            "city": city,
            "property_type": "apartment",
            "typology": typology_from_title(f"{card.get('type_text', '')} {title}"),
            "floor": _extract_floor(f"{card.get('features_text', '')} {description}"),
            "has_garage": "garagem" in features_lower or "estacionamento" in features_lower,
            "is_rented": is_rented(combined_text) if not is_rent else False,
            "lifetime_rent": is_lifetime_rent(combined_text) if not is_rent else False,
            "active": True,
            "inactive_since": None,
            "last_seen": now,
            "updated_at": now,
            "_raw_json": {
                **ld,
                "uid": uid,
                "url": url,
                "locationText": card.get("location_text"),
                "featuresText": card.get("features_text"),
                "fullDescription": description,
            },
        }
    except Exception:
        logger.debug("Failed to parse Casa Sapo card", exc_info=True)
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
        cards = response.get("cards")
        if cards is None and "html" in response:
            cards = extract_cards(response["html"])
        for card in cards or []:
            listing = parse_card(card, target_city, min_price, max_price, listing_type)
            if not listing or listing["id"] in seen:
                continue
            seen.add(listing["id"])
            listings.append(listing)

    if listing_type == "buy":
        rented = sum(1 for item in listings if item.get("is_rented"))
        logger.info("Casa Sapo parsed %d unique listings — %d flagged as rented", len(listings), rented)
    else:
        logger.info("Casa Sapo parsed %d unique rental listings", len(listings))

    return listings
