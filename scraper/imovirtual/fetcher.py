import json
import logging
import time
import unicodedata
from typing import Optional

from curl_cffi import requests as curl_requests

from config import MAX_PRICE, REQUEST_DELAY
from scraper.imovirtual.constants import BASE_URL
from scraper.utils import is_rented

logger = logging.getLogger(__name__)

SEARCH_URL = BASE_URL + "comprar/apartamento/porto/"
API_PATH = "pt/resultados/comprar/apartamento/porto/porto.json"
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


def _get_build_id(session) -> Optional[str]:
    resp = session.get(
        SEARCH_URL,
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


def _fetch_page(session, build_id: str, page: int) -> Optional[dict]:
    url = f"{BASE_URL}_next/data/{build_id}/{API_PATH}?page={page}&{SORT_PARAMS}"
    resp = session.get(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Language": "pt-PT,pt;q=0.9",
            "Referer": SEARCH_URL,
            "x-nextjs-data": "1",
        },
    )

    if resp.status_code != 200:
        logger.error("Page %d returned status %d", page, resp.status_code)
        return None

    return resp.json().get("pageProps", {}).get("data", {}).get("searchAds")


def _fetch_detail(session, url: str) -> tuple[Optional[str], Optional[str]]:
    resp = session.get(
        url,
        headers={
            "Accept": "text/html",
            "Accept-Language": "pt-PT,pt;q=0.9",
        },
    )

    if resp.status_code != 200:
        return None, None

    html = resp.text
    data = extract_next_data(html)
    description = (data or {}).get("pageProps", {}).get("ad", {}).get("description")

    return description, html


def verify_still_active(id_url_pairs: list[tuple[str, str]]) -> set[str]:
    """Check each listing URL and return the IDs that are still live on the site."""
    if not id_url_pairs:
        return set()

    session = curl_requests.Session(impersonate="chrome")
    still_active = set()

    for i, (listing_id, url) in enumerate(id_url_pairs):
        try:
            resp = session.get(url, headers={"Accept": "text/html", "Accept-Language": "pt-PT,pt;q=0.9"})
            if resp.status_code == 200:
                data = extract_next_data(resp.text)
                if (data or {}).get("pageProps", {}).get("ad"):
                    still_active.add(listing_id)
        except Exception:
            logger.debug("Failed to verify listing %s", listing_id, exc_info=True)

        if (i + 1) % 20 == 0:
            logger.info("Verified %d/%d candidates", i + 1, len(id_url_pairs))

        time.sleep(REQUEST_DELAY)

    return still_active


def fetch() -> list[dict]:
    session = curl_requests.Session(impersonate="chrome")

    build_id = _get_build_id(session)
    if not build_id:
        return []

    responses = []
    page = 0

    while True:
        page += 1
        search_data = _fetch_page(session, build_id, page)
        if not search_data:
            break

        items = search_data.get("items", [])
        pagination = search_data.get("pagination", {})
        total_pages = pagination.get("totalPages", 0)
        total_items = pagination.get("totalItems", 0)
        cheapest = min_price(items)

        responses.append(search_data)
        logger.info(
            "Page %d/%d: %d listings (total: %d, min: %s)",
            page,
            total_pages,
            len(items),
            total_items,
            f"{cheapest}€" if cheapest else "?",
        )

        if cheapest and cheapest > MAX_PRICE:
            logger.info("Passed %d€ ceiling — stopping", MAX_PRICE)
            break

        if page >= total_pages or not items:
            break

        time.sleep(REQUEST_DELAY)

    return responses


def fetch_details(listings: list[dict]) -> list[dict]:
    if not listings:
        return listings

    # Only enrich listings already flagged as rented from title.
    # A lifetime-rent listing will always have rental keywords in its title too,
    # so we don't need to fetch details for every listing.
    candidates = [listing for listing in listings if listing.get("is_rented")]
    if not candidates:
        return listings

    session = curl_requests.Session(impersonate="chrome")
    enriched = 0

    for i, listing in enumerate(candidates):
        url = listing.get("url", "")
        if not url:
            continue

        description, html = _fetch_detail(session, url)
        if description:
            listing["description"] = description
            listing["is_rented"] = is_rented(f"{listing.get('title', '')} {description}")
            listing["lifetime_rent"] = _is_lifetime_rent(description)
            enriched += 1
        else:
            listing["is_rented"] = is_rented(listing.get("title", ""))
        if html:
            listing["_raw_html"] = html

        if (i + 1) % 20 == 0:
            logger.info("Detail %d/%d fetched", i + 1, len(candidates))

        time.sleep(REQUEST_DELAY)

    logger.info("Enriched %d/%d rented candidates with full description", enriched, len(candidates))
    return listings
