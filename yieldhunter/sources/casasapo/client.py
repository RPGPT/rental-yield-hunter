"""Casa Sapo HTTP client with price-ascending pagination and polite 429 retry/backoff."""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from curl_cffi import requests as curl_requests

from yieldhunter.sources.casasapo.constants import (
    BASE_URL,
    CASASAPO_PAGE_DELAY,
    CASASAPO_RETRY_BACKOFFS,
    CITY_SLUGS,
    PORTO_DISTRICT_CODE,
)
from yieldhunter.sources.casasapo.parser import extract_cards, parse_price
from yieldhunter.sources.http import HTML_HEADERS

logger = logging.getLogger(__name__)


def build_search_url(city: str, listing_type: str = "buy", page: int = 1, city_slugs: Optional[dict] = None) -> str:
    slugs = city_slugs if city_slugs is not None else CITY_SLUGS
    if city not in slugs:
        raise ValueError(f"Unsupported Casa Sapo city: {city!r}. Supported: {list(slugs)}")
    action = "arrendar-apartamentos" if listing_type == "rent" else "comprar-apartamentos"
    url = f"{BASE_URL}/{action}/mais-baratos/{slugs[city]}/?sa={PORTO_DISTRICT_CODE}"
    if page > 1:
        url += f"&pn={page}"
    return url


def _get_page_with_retry(session, url: str):
    resp = session.get(url, headers=HTML_HEADERS)
    if resp.status_code != 429:
        return resp
    for wait_s in CASASAPO_RETRY_BACKOFFS:
        logger.warning("[CasaSapo] 429 rate-limit on %s — backing off %.0fs", url, wait_s)
        time.sleep(wait_s)
        resp = session.get(url, headers=HTML_HEADERS)
        if resp.status_code != 429:
            return resp
    return resp


def _has_next_page(html: str, next_page: int) -> bool:
    return bool(re.search(rf"[?&]pn={next_page}(?:[&\"'#]|$)", html))


def fetch_with_context(
    city: str,
    listing_type: str = "buy",
    max_price: Optional[int] = None,
    city_slugs: Optional[dict] = None,
) -> tuple[list[dict], bool]:
    """Fetch Casa Sapo search pages and return ``(responses, complete)``."""
    build_search_url(city, listing_type=listing_type, page=1, city_slugs=city_slugs)

    session = curl_requests.Session(impersonate="chrome")
    responses: list[dict] = []
    seen_uids: set[str] = set()
    page = 1
    complete = True

    while True:
        url = build_search_url(city, listing_type=listing_type, page=page, city_slugs=city_slugs)
        resp = _get_page_with_retry(session, url)
        if resp.status_code != 200:
            logger.error("[CasaSapo/%s] Page %d returned status %d", city, page, resp.status_code)
            complete = False
            break

        html = resp.text
        if "<title>Site Offline</title>" in html:
            logger.error("[CasaSapo/%s] Page %d returned rate-limit offline page", city, page)
            complete = False
            break

        cards = extract_cards(html)
        new_cards = [c for c in cards if c["uid"] not in seen_uids]
        if not new_cards:
            break

        for c in new_cards:
            seen_uids.add(c["uid"])

        responses.append({"page": page, "cards": new_cards})

        prices = [
            p
            for c in new_cards
            if (
                p := (
                    parse_price((c.get("ld") or {}).get("offers", {}).get("price")) or parse_price(c.get("price_text"))
                )
            )
            is not None
        ]
        cheapest = min(prices) if prices else None
        logger.info(
            "[CasaSapo/%s] Page %d: %d listings (min: %s)",
            city,
            page,
            len(new_cards),
            f"{cheapest}€" if cheapest else "?",
        )

        if max_price and cheapest is not None and cheapest > max_price:
            logger.info("[CasaSapo/%s] Min price %d exceeds ceiling %d — stopping", city, cheapest, max_price)
            break

        if not _has_next_page(html, page + 1):
            break

        page += 1
        time.sleep(CASASAPO_PAGE_DELAY)

    return responses, complete


def fetch(
    city: str,
    listing_type: str = "buy",
    max_price: Optional[int] = None,
    city_slugs: Optional[dict] = None,
) -> list[dict]:
    responses, _ = fetch_with_context(city, listing_type=listing_type, max_price=max_price, city_slugs=city_slugs)
    return responses
