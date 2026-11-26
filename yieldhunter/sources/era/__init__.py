"""ERA.pt buy and rental scraper classes."""

from __future__ import annotations

from typing import Optional

from yieldhunter import config
from yieldhunter.sources.base import Scraper
from yieldhunter.sources.era.client import fetch_details, fetch_with_context
from yieldhunter.sources.era.constants import BUSINESS_TYPE_BUY, BUSINESS_TYPE_RENT, CITY_CONFIG
from yieldhunter.sources.era.parser import parse


class ERABaseScraper(Scraper):
    CITY_CONFIG = CITY_CONFIG
    MIN_PRICE: int = 0
    MAX_PRICE: int = 0
    BUSINESS_TYPE_ID: int = BUSINESS_TYPE_BUY

    def __init__(self, city: str):
        self.city = city
        self._session = None
        self._token: Optional[str] = None

    def fetch(self) -> list[dict]:
        responses, complete, session, token = fetch_with_context(
            self.city,
            self.CITY_CONFIG,
            self.BUSINESS_TYPE_ID,
            max_price=self.MAX_PRICE,
        )
        self.last_fetch_complete = complete
        self._session = session
        self._token = token
        return responses

    def parse(self, responses: list[dict]) -> list[dict]:
        listing_type = "rent" if self.BUSINESS_TYPE_ID == BUSINESS_TYPE_RENT else "buy"
        return parse(
            responses,
            target_city=self.city,
            min_price=self.MIN_PRICE,
            max_price=self.MAX_PRICE,
            listing_type=listing_type,
        )


class ERABuyScraper(ERABaseScraper):
    MIN_PRICE = config.MIN_PRICE
    MAX_PRICE = config.MAX_PRICE
    BUSINESS_TYPE_ID = BUSINESS_TYPE_BUY

    def enrich(self, listings: list[dict]) -> list[dict]:
        return fetch_details(
            listings,
            self.city,
            self.CITY_CONFIG,
            session=self._session,
            token=self._token,
        )


class ERARentalScraper(ERABaseScraper):
    MIN_PRICE = config.MIN_RENTAL_PRICE
    MAX_PRICE = config.MAX_RENTAL_PRICE
    BUSINESS_TYPE_ID = BUSINESS_TYPE_RENT


__all__ = ["ERABaseScraper", "ERABuyScraper", "ERARentalScraper"]
