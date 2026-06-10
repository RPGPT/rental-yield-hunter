import logging
import re
import time
from typing import Optional

from curl_cffi import requests as curl_requests

from config import REQUEST_DELAY
from scraper.era.constants import BASE_URL, DETAIL_MODULE_ID, DETAIL_TAB_ID, MODULE_ID, SEARCH_API_PATH, TAB_ID
from scraper.utils import is_lifetime_rent, is_rented

logger = logging.getLogger(__name__)


def _get_token(session, search_url: str) -> Optional[tuple[str, str, str]]:
    """Fetch search page, return (csrf_token, module_id, tab_id) or None."""
    resp = session.get(
        search_url,
        headers={"Accept": "text/html", "Accept-Language": "pt-PT,pt;q=0.9"},
    )
    if resp.status_code != 200:
        logger.error("Token page %s returned status %d", search_url, resp.status_code)
        return None

    html = resp.text
    m = re.search(r'__RequestVerificationToken[^>]*?value="([^"]+)"', html)
    if not m:
        logger.error("Could not extract RequestVerificationToken from %s", search_url)
        return None

    token = m.group(1)
    mid = re.search(r'data-moduleid="(\d+)"', html)
    tid = re.search(r'data-tabid="(\d+)"', html)
    module_id = mid.group(1) if mid else MODULE_ID
    tab_id = tid.group(1) if tid else TAB_ID

    logger.info("ERA token obtained (ModuleId=%s, TabId=%s)", module_id, tab_id)
    return token, module_id, tab_id


def _parse_price_quick(item: dict, is_rent: bool) -> Optional[int]:
    """Fast price parse for pagination ceiling check."""
    key = "RentPrice" if is_rent else "SellPrice"
    raw = (item.get(key) or {}).get("Value") or ""
    raw = raw.replace("€", "").replace("\xa0", "").replace(" ", "").strip()
    if not raw:
        return None
    raw = raw.replace(".", "").replace(",", ".")
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return None


def fetch(city: str, city_config: dict, business_type_id: int, max_price: Optional[int] = None) -> list[dict]:
    """Fetch all search pages for *city* from the ERA API.

    Returns a list of raw API response dicts (one per page).
    """
    if city not in city_config:
        raise ValueError(f"Unsupported ERA city: {city!r}. Supported: {list(city_config)}")

    location_id, search_path = city_config[city]
    search_url = BASE_URL + search_path
    is_rent = business_type_id == 2

    session = curl_requests.Session(impersonate="chrome")
    token_data = _get_token(session, search_url)
    if not token_data:
        return []

    token, module_id, tab_id = token_data
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "RequestVerificationToken": token,
        "ModuleId": module_id,
        "TabId": tab_id,
        "Referer": search_url,
        "Accept-Language": "pt-PT,pt;q=0.9",
    }

    results = []
    page = 1

    while True:
        body = {
            "businessTypeId": [business_type_id],
            "propertiesTypeId": [1],
            "locationId": [location_id],
            "page": page,
            "order": 3,
        }

        resp = session.post(BASE_URL + SEARCH_API_PATH, json=body, headers=headers)

        if resp.status_code != 200:
            logger.error("[ERA/%s] Page %d returned status %d", city, page, resp.status_code)
            break

        data = resp.json()
        total_pages = data.get("TotalPages", 0)
        property_list = data.get("PropertyList", [])

        if not property_list:
            break

        results.append(data)
        logger.info("[ERA/%s] Page %d/%d: %d listings", city, page, total_pages, len(property_list))

        if max_price:
            prices = [_parse_price_quick(p, is_rent) for p in property_list]
            valid = [p for p in prices if p is not None]
            if valid and min(valid) > max_price:
                logger.info("[ERA/%s] Min price %d exceeds ceiling %d — stopping", city, min(valid), max_price)
                break

        if page >= total_pages:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return results


def _fetch_single_detail(session, token: str, reference: str, referer: str) -> Optional[str]:
    """Return the Description text for one ERA listing, or None on failure."""
    resp = session.get(
        BASE_URL + "API/ServicesModule/Property/PropertyDetailByReference",
        params={"reference": reference},
        headers={
            "Accept": "application/json",
            "RequestVerificationToken": token,
            "ModuleId": DETAIL_MODULE_ID,
            "TabId": DETAIL_TAB_ID,
            "Referer": referer,
            "Accept-Language": "pt-PT,pt;q=0.9",
        },
    )
    if resp.status_code == 200:
        return resp.json().get("Description") or ""
    logger.debug("[ERA] Detail fetch for ref %s returned %d", reference, resp.status_code)
    return None


def fetch_details(listings: list[dict], city: str, city_config: dict) -> list[dict]:
    """Enrich all buy listings with full description for is_rented / lifetime_rent detection."""
    if not listings:
        return listings

    _, search_path = city_config[city]
    search_url = BASE_URL + search_path

    session = curl_requests.Session(impersonate="chrome")
    token_data = _get_token(session, search_url)
    if not token_data:
        logger.warning("[ERA/%s] Could not get token — skipping detail enrichment", city)
        return listings

    token, _, _ = token_data  # CSRF token is session-wide; detail module IDs are hardcoded
    enriched = 0

    for i, listing in enumerate(listings):
        reference = listing["id"].removeprefix("era-")
        description = _fetch_single_detail(session, token, reference, listing.get("url", ""))

        if description is not None:
            combined = f"{listing.get('title', '')} {description}".strip()
            listing["description"] = description
            listing["is_rented"] = is_rented(combined)
            listing["lifetime_rent"] = is_lifetime_rent(combined)
            enriched += 1

        if (i + 1) % 20 == 0:
            logger.info("[ERA/%s] Detail %d/%d fetched", city, i + 1, len(listings))

        time.sleep(REQUEST_DELAY)

    logger.info("[ERA/%s] Enriched %d/%d listings with description", city, enriched, len(listings))
    return listings
