"""Pipeline step for extracting current rent and contract expiry from tenanted buy listings.

Optimization: ``ImovirtualBuyScraper.enrich`` and ``ERABuyScraper.enrich`` already fetch and
persist full descriptions (on ``listings.description`` and ``raw_data.raw_json['fullDescription']``)
for every active rented listing. Reading that stored text avoids N×2s redundant HTTP calls and
eliminates calling the Imovirtual endpoint on ERA URLs. An HTTP detail fetch is only performed as
a fallback when an Imovirtual listing is missing ``fullDescription`` in ``raw_data``.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from curl_cffi import requests as curl_requests

from yieldhunter.analysis.contracts import extract_rent_and_expiry
from yieldhunter.config import REQUEST_DELAY
from yieldhunter.db.repository import get_rented_listings_for_extraction, upsert_contract_details
from yieldhunter.db.session import session_scope
from yieldhunter.pipeline.stats import city_slug, write_stats_file
from yieldhunter.sources.imovirtual.client import _fetch_detail, _get_build_id
from yieldhunter.sources.imovirtual.constants import BASE_URL, BUY_CITY_PATHS

logger = logging.getLogger(__name__)


def _backfill_imovirtual_text(listing: dict, state: dict) -> tuple[str, str]:
    """Fetch detail from Imovirtual only when stored ``raw_data`` lacks ``fullDescription``."""
    url = listing.get("url", "")
    if not url or not state.get("can_fetch", True):
        return listing.get("description", ""), ""

    if "session" not in state:
        session = curl_requests.Session(impersonate="chrome")
        city_key = listing.get("city") if listing.get("city") in BUY_CITY_PATHS else next(iter(BUY_CITY_PATHS))
        search_path, _ = BUY_CITY_PATHS[city_key]
        build_id = _get_build_id(session, BASE_URL + search_path)
        if not build_id:
            logger.warning("Could not get Imovirtual buildId for contract backfill")
            state["can_fetch"] = False
            return listing.get("description", ""), ""
        state["session"] = session
        state["build_id"] = build_id

    detail = _fetch_detail(state["session"], url, state["build_id"])
    time.sleep(REQUEST_DELAY)
    if detail:
        return detail.get("description") or "", detail.get("full_description") or ""
    return listing.get("description", ""), ""


def run_extract_contracts(city: Optional[str] = None) -> dict:
    """Extract contract rent and expiry for active tenanted buy listings."""
    label = city or "all cities"
    logger.info("Extracting contract details (%s)…", label)

    with session_scope() as db:
        listings = get_rented_listings_for_extraction(db, city=city)

    slug = city_slug(city)
    if not listings:
        logger.info("No rented listings to process (%s)", label)
        stats = {"type": "contracts", "city": city or "all", "processed": 0, "with_rent": 0, "with_expiry": 0}
        write_stats_file(f"stats-contracts-{slug}.json", stats)
        return stats

    logger.info("Found %d rented listings to process (%s)", len(listings), label)

    details_to_upsert: list[dict] = []
    with_rent = 0
    with_expiry = 0
    backfill_state: dict = {}

    for listing in listings:
        if listing["source"] == "imovirtual" and not listing["has_full_description"]:
            desc, full_desc = _backfill_imovirtual_text(listing, backfill_state)
        else:
            desc = listing["description"]
            full_desc = listing["full_description"]

        combined = f"{listing['title']} {desc} {full_desc}".strip()
        if not combined:
            continue

        result = extract_rent_and_expiry(combined)
        if result["current_rent_amount"] is not None or result["contract_expiry_date"] is not None:
            details_to_upsert.append(
                {
                    "listing_id": listing["id"],
                    "current_rent": result["current_rent_amount"],
                    "contract_expiry_date": result["contract_expiry_date"],
                    "raw_rent_text": result["raw_rent_text"],
                    "raw_expiry_text": result["raw_expiry_text"],
                    "confidence": result["confidence"],
                }
            )
            if result["current_rent_amount"] is not None:
                with_rent += 1
            if result["contract_expiry_date"] is not None:
                with_expiry += 1

    if details_to_upsert:
        with session_scope() as db:
            upsert_contract_details(db, details_to_upsert)

    stats = {
        "type": "contracts",
        "city": city or "all",
        "processed": len(listings),
        "with_rent": with_rent,
        "with_expiry": with_expiry,
        "extracted": len(details_to_upsert),
    }
    write_stats_file(f"stats-contracts-{slug}.json", stats)
    logger.info(
        "Done — %d/%d listings yielded contract data (%d rent, %d expiry) (%s)",
        len(details_to_upsert),
        len(listings),
        with_rent,
        with_expiry,
        label,
    )
    return stats
