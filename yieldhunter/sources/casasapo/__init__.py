"""Casa Sapo buy and rental scraper classes."""

from __future__ import annotations

from yieldhunter import config
from yieldhunter.sources.base import Scraper
from yieldhunter.sources.casasapo.client import fetch_with_context
from yieldhunter.sources.casasapo.constants import CITY_SLUGS
from yieldhunter.sources.casasapo.parser import parse


class CasaSapoBaseScraper(Scraper):
    CITY_SLUGS = CITY_SLUGS
    MIN_PRICE: int = 0
    MAX_PRICE: int = 0
    LISTING_TYPE: str = "buy"

    def __init__(self, city: str):
        self.city = city

    def fetch(self) -> list[dict]:
        responses, complete = fetch_with_context(
            self.city,
            listing_type=self.LISTING_TYPE,
            max_price=self.MAX_PRICE,
            city_slugs=self.CITY_SLUGS,
        )
        self.last_fetch_complete = complete
        return responses

    def parse(self, responses: list[dict]) -> list[dict]:
        return parse(
            responses,
            target_city=self.city,
            min_price=self.MIN_PRICE,
            max_price=self.MAX_PRICE,
            listing_type=self.LISTING_TYPE,
        )


class CasaSapoBuyScraper(CasaSapoBaseScraper):
    MIN_PRICE = config.MIN_PRICE
    MAX_PRICE = config.MAX_PRICE
    LISTING_TYPE = "buy"


class CasaSapoRentalScraper(CasaSapoBaseScraper):
    MIN_PRICE = config.MIN_RENTAL_PRICE
    MAX_PRICE = config.MAX_RENTAL_PRICE
    LISTING_TYPE = "rent"


__all__ = ["CasaSapoBaseScraper", "CasaSapoBuyScraper", "CasaSapoRentalScraper"]
