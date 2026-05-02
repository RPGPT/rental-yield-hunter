import json
import logging
import os
import random
import time
from typing import Optional, List

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

# Idealista.pt — Porto apartments for sale
BASE_URL = "https://www.idealista.pt/comprar-casas/porto/com-preco-max_500000/"
MAX_PAGES = 5

# Rotate user agents to reduce fingerprinting
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Free proxy cache — fetched once per run
_proxy_cache = None


def _get_free_proxies() -> List[str]:
    """Fetch free HTTPS proxies from free-proxy-list.net."""
    global _proxy_cache
    if _proxy_cache is not None:
        return _proxy_cache

    try:
        resp = curl_requests.get("https://free-proxy-list.net/", impersonate="chrome")
        soup = BeautifulSoup(resp.text, "lxml")
        proxies = []
        for row in soup.select("table.table tbody tr"):
            cols = row.select("td")
            if len(cols) >= 7 and cols[6].text.strip().lower() == "yes":
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                proxies.append(f"http://{ip}:{port}")
        logger.info("Fetched %d free HTTPS proxies", len(proxies))
        _proxy_cache = proxies
        return proxies
    except Exception as e:
        logger.warning("Failed to fetch proxies: %s", e)
        _proxy_cache = []
        return []


def _make_request(session, url: str, proxies: List[str]) -> Optional[str]:
    """
    Make an HTTP request with proxy rotation and retry logic.
    Returns HTML text or None on failure.
    """
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.idealista.pt/",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "1",
    }

    # Try with proxies first (shuffle to randomize)
    proxy_list = list(proxies)
    random.shuffle(proxy_list)

    for proxy in proxy_list[:5]:  # Try up to 5 proxies
        try:
            resp = session.get(url, headers=headers, proxy=proxy, timeout=15)
            if resp.status_code == 200 and len(resp.text) > 5000:
                if "captcha-delivery" not in resp.text and "bloqueado" not in resp.text:
                    logger.info("Success via proxy %s", proxy)
                    return resp.text
            logger.debug("Proxy %s: status %d or blocked", proxy, resp.status_code)
        except Exception as e:
            logger.debug("Proxy %s failed: %s", proxy, e)
            continue

    # Fallback: direct connection (no proxy)
    try:
        resp = session.get(url, headers=headers, timeout=15)
        if resp.status_code == 200 and len(resp.text) > 5000:
            if "captcha-delivery" not in resp.text:
                logger.info("Success via direct connection")
                return resp.text
        logger.warning("Direct request blocked (status=%d, len=%d)", resp.status_code, len(resp.text))
    except Exception as e:
        logger.warning("Direct request failed: %s", e)

    return None


def _parse_listing_page(html: str) -> List[dict]:
    """
    Parse an Idealista listing page HTML and extract raw listing data.
    XPath selectors based on Scrapy-Idealista, adapted for BS4 + idealista.pt.
    """
    soup = BeautifulSoup(html, "lxml")
    listings = []

    # Idealista uses article.item or div.item-info-container
    items = soup.select("article.item")
    if not items:
        items = soup.select(".item-info-container")

    for item in items:
        try:
            # Title + link
            link_el = item.select_one("a.item-link")
            if not link_el:
                continue

            title = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            if href and not href.startswith("http"):
                url = "https://www.idealista.pt" + href
            else:
                url = href

            # Price
            price_el = item.select_one(".item-price")
            price_text = price_el.get_text(strip=True) if price_el else ""

            # Details (area, rooms, floor)
            details = item.select(".item-detail")
            area_text = ""
            rooms_text = ""
            for detail in details:
                text = detail.get_text(strip=True)
                if "m²" in text or "m2" in text:
                    area_text = text
                elif "hab" in text.lower() or "quarto" in text.lower():
                    rooms_text = text

            # Description (may contain tenant keywords)
            desc_el = item.select_one(".item-description") or item.select_one(".ellipsis")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # Listing ID from URL
            listing_id = href.rstrip("/").split("/")[-1] if href else ""

            listings.append({
                "id": listing_id,
                "title": title,
                "price_text": price_text,
                "area_text": area_text,
                "rooms_text": rooms_text,
                "description": description,
                "url": url,
            })
        except Exception as e:
            logger.debug("Failed to parse item: %s", e)
            continue

    return listings


def _get_next_page_url(html: str) -> Optional[str]:
    """Extract the next page URL from Idealista pagination."""
    soup = BeautifulSoup(html, "lxml")
    # Scrapy-Idealista uses: a.icon-arrow-right-after
    next_link = soup.select_one("a.icon-arrow-right-after") or soup.select_one(".next a")
    if next_link:
        href = next_link.get("href", "")
        if href and not href.startswith("http"):
            return "https://www.idealista.pt" + href
        return href
    return None


def fetch() -> List[dict]:
    """
    Fetch property listings from idealista.pt for Porto.

    Uses free proxy rotation and user-agent randomization to attempt
    to bypass DataDome bot protection.

    ⚠️  Free proxies are unreliable. For consistent results, set the
    PROXY_URL environment variable with a paid residential proxy:
        export PROXY_URL=http://user:pass@proxy.service.com:8080

    Returns a list of dicts with an 'items' key containing raw listings.
    """
    session = curl_requests.Session(impersonate="chrome")

    # Prefer paid proxy from env var if available
    env_proxy = os.environ.get("PROXY_URL", "")
    if env_proxy:
        logger.info("Using paid proxy from PROXY_URL env var")
        proxies = [env_proxy]
    else:
        proxies = _get_free_proxies()
        if not proxies:
            logger.warning("No proxies available — will try direct connection only")

    all_listings = []
    url = BASE_URL

    for page_num in range(1, MAX_PAGES + 1):
        logger.info("Fetching page %d: %s", page_num, url)

        html = _make_request(session, url, proxies)
        if not html:
            logger.warning("Failed to fetch page %d — stopping", page_num)
            break

        page_listings = _parse_listing_page(html)
        logger.info("Page %d: extracted %d listings", page_num, len(page_listings))

        if not page_listings:
            break

        all_listings.extend(page_listings)

        # Get next page
        next_url = _get_next_page_url(html)
        if not next_url:
            logger.info("No more pages")
            break
        url = next_url

        # Respectful delay (3-6s to avoid detection)
        delay = random.uniform(3, 6)
        logger.info("Waiting %.1fs...", delay)
        time.sleep(delay)

    return [{"items": all_listings}] if all_listings else []
