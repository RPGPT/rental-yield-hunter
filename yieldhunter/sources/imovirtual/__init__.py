"""Imovirtual buy and rental scraper classes."""

from __future__ import annotations

from typing import Optional

from yieldhunter import config
from yieldhunter.sources.base import Scraper
from yieldhunter.sources.imovirtual.client import fetch_details, fetch_with_context
from yieldhunter.sources.imovirtual.constants import BUY_CITY_PATHS, RENTAL_CITY_PATHS
from yieldhunter.sources.imovirtual.parser import parse


class ImovirtualBaseScraper(Scraper):
    """Common scraping logic for Imovirtual; subclasses declare ``CITY_PATHS`` and price bounds."""

    CITY_PATHS: dict = {}
    MIN_PRICE: int = 0
    MAX_PRICE: int = 0

    def __init__(self, city: str):
        self.city = city
        self.known_rented_ids: set[str] = set()
        self._session = None
        self._build_id: Optional[str] = None

    def fetch(self) -> list[dict]:
        responses, complete, session, build_id = fetch_with_context(
            self.city,
            city_paths=self.CITY_PATHS,
            max_price=self.MAX_PRICE,
        )
        self.last_fetch_complete = complete
        self._session = session
        self._build_id = build_id
        return responses

    def parse(self, responses: list[dict]) -> list[dict]:
        return parse(
            responses,
            target_city=self.city,
            min_price=self.MIN_PRICE,
            max_price=self.MAX_PRICE,
        )

    def enrich(self, listings: list[dict]) -> list[dict]:
        return fetch_details(
            listings,
            self.city,
            city_paths=self.CITY_PATHS,
            known_rented_ids=self.known_rented_ids,
            session=self._session,
            build_id=self._build_id,
        )


class ImovirtualBuyScraper(ImovirtualBaseScraper):
    CITY_PATHS = BUY_CITY_PATHS
    MIN_PRICE = config.MIN_PRICE
    MAX_PRICE = config.MAX_PRICE


class ImovirtualRentalScraper(ImovirtualBaseScraper):
    CITY_PATHS = RENTAL_CITY_PATHS
    MIN_PRICE = config.MIN_RENTAL_PRICE
    MAX_PRICE = config.MAX_RENTAL_PRICE

    def enrich(self, listings: list[dict]) -> list[dict]:
        return listings


ImovirtualScraper = ImovirtualBuyScraper

__all__ = [
    "ImovirtualBaseScraper",
    "ImovirtualBuyScraper",
    "ImovirtualRentalScraper",
    "ImovirtualScraper",
]
