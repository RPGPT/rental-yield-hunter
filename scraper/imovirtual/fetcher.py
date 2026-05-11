import json
import logging
import time
import unicodedata
from typing import Optional

from curl_cffi import requests as curl_requests

from config import MAX_PRICE, REQUEST_DELAY
from scraper.imovirtual.constants import BASE_URL, BUY_CITY_PATHS
from scraper.utils import is_rented

logger = logging.getLogger(__name__)

SORT_PARAMS = "by=PRICE&direction=ASC"


def extract_next_data(html: str) -> Optional[dict]:
    marker = 'id="__NEXT_DATA__"'
    start = html.find(marker)
    if start == -1:
        return None
    json_start = html.find(">", start) + 1
    json_end = html.find("</script>", json_start)
    return json.loads(html[json_start:json_end])


def min_price(items: list) -> Optional[int]:
    for item in items:
        value = (item.get("totalPrice") or {}).get("value")
        if value is not None:
            return int(value)
    return None


def _is_lifetime_rent(text: str) -> bool:
    normalized = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return "vitalicio" in stripped or "vitalicia" in stripped


def _get_build_id(session, search_url: str) -> Optional[str]:
    resp = session.get(
        search_url,
        headers={"Accept": "text/html", "Accept-Language": "pt-PT,pt;q=0.9"},
    )
    if resp.status_code != 200:
        logger.error("HTML page returned status %d", resp.status_code)
        return None

    data = extract_next_data(resp.text)
    build_id = data.get("buildId") if data else None

    if not build_id:
        logger.error("Could not extract buildId")
        return None

    logger.info("buildId: %s", build_id)
    return build_id


def _fetch_page(session, build_id: str, api_path: str, search_url: str, page: int) -> Optional[dict]:
    url = f"{BASE_URL}_next/data/{build_id}/{api_path}?page={page}&{SORT_PARAMS}"
    resp = session.get(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Language": "pt-PT,pt;q=0.9",
            "Referer": search_url,
            "x-nextjs-data": "1",
        },
    )

    if resp.status_code != 200:
        logger.error("Page %d returned status %d", page, resp.status_code)
        return None

    return resp.json().get("pageProps", {}).get("data", {}).get("searchAds")


def _fetch_detail(session, url: str, build_id: str) -> Optional[dict]:
    """Return {"description": ..., "full_description": ...} for the listing, or None on failure."""
    path = url.replace(BASE_URL, "").lstrip("/")
    api_url = f"{BASE_URL}_next/data/{build_id}/{path}.json"
    resp = session.get(
        api_url,
        headers={
            "Accept": "application/json",
            "Accept-Language": "pt-PT,pt;q=0.9",
            "Referer": url,
            "x-nextjs-data": "1",
        },
    )
    if resp.status_code == 200:
        ad = resp.json().get("pageProps", {}).get("ad", {})
        return {
            "description": ad.get("description"),
            "full_description": ad.get("fullDescription"),
        }
    return None


def fetch(city: str, city_paths: Optional[dict] = None, max_price: Optional[int] = None) -> list[dict]:
    resolved_paths = city_paths if city_paths is not None else BUY_CITY_PATHS
    resolved_max_price = max_price if max_price is not None else MAX_PRICE

    if city not in resolved_paths:
        raise ValueError(f"Unsupported city: {city!r}. Supported: {list(resolved_paths)}")

    search_path, api_path = resolved_paths[city]
    search_url = BASE_URL + search_path

    session = curl_requests.Session(impersonate="chrome")

    build_id = _get_build_id(session, search_url)
    if not build_id:
        return []

    responses = []
    page = 0

    while True:
        page += 1
        search_data = _fetch_page(session, build_id, api_path, search_url, page)
        if not search_data:
            break

        items = search_data.get("items", [])
        pagination = search_data.get("pagination", {})
        total_pages = pagination.get("totalPages", 0)
        total_items = pagination.get("totalItems", 0)
        cheapest = min_price(items)

        responses.append(search_data)
        logger.info(
            "[%s] Page %d/%d: %d listings (total: %d, min: %s)",
            city,
            page,
            total_pages,
            len(items),
            total_items,
            f"{cheapest}€" if cheapest else "?",
        )

        if cheapest and cheapest > resolved_max_price:
            logger.info("[%s] Passed %d€ ceiling — stopping", city, resolved_max_price)
            break

        if page >= total_pages or not items:
            break

        time.sleep(REQUEST_DELAY)

    return responses


def fetch_details(listings: list[dict], city: str, city_paths: Optional[dict] = None) -> list[dict]:
    if not listings:
        return listings

    candidates = [listing for listing in listings if listing.get("is_rented")]
    if not candidates:
        return listings

    resolved_paths = city_paths if city_paths is not None else BUY_CITY_PATHS

    if city not in resolved_paths:
        raise ValueError(f"Unsupported city: {city!r}. Supported: {list(resolved_paths)}")

    search_path, _ = resolved_paths[city]
    search_url = BASE_URL + search_path

    session = curl_requests.Session(impersonate="chrome")
    build_id = _get_build_id(session, search_url)
    if not build_id:
        logger.warning("Could not get buildId — skipping detail enrichment")
        return listings
    enriched = 0

    for i, listing in enumerate(candidates):
        url = listing.get("url", "")
        if not url:
            continue

        detail = _fetch_detail(session, url, build_id)
        if detail:
            description = detail["description"] or ""
            full_description = detail["full_description"] or ""
            # Store the primary description; check lifetime_rent against both
            # fields because sellers often put "vitalícia" in fullDescription only.
            combined = f"{description} {full_description}".strip()
            listing["description"] = description
            listing["is_rented"] = is_rented(f"{listing.get('title', '')} {combined}")
            listing["lifetime_rent"] = _is_lifetime_rent(combined)
            if isinstance(listing.get("_raw_json"), dict):
                listing["_raw_json"]["fullDescription"] = full_description
            enriched += 1
        else:
            listing["is_rented"] = is_rented(listing.get("title", ""))

        if (i + 1) % 20 == 0:
            logger.info("[%s] Detail %d/%d fetched", city, i + 1, len(candidates))

        time.sleep(REQUEST_DELAY)

    logger.info("[%s] Enriched %d/%d rented candidates with full description", city, enriched, len(candidates))
    return listings
