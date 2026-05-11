import config
from scraper.base import Scraper
from scraper.imovirtual.constants import BUY_CITY_PATHS, RENTAL_CITY_PATHS
from scraper.imovirtual.fetcher import fetch, fetch_details
from scraper.imovirtual.parser import parse


class ImovirtualBaseScraper(Scraper):
    """Common scraping logic for Imovirtual. Subclasses declare CITY_PATHS and price bounds."""

    CITY_PATHS: dict = {}
    MIN_PRICE: int = 0
    MAX_PRICE: int = 0

    def __init__(self, city: str):
        self.city = city

    def fetch(self):
        return fetch(self.city, city_paths=self.CITY_PATHS, max_price=self.MAX_PRICE)

    def parse(self, responses):
        return parse(
            responses,
            target_city=self.city,
            min_price=self.MIN_PRICE,
            max_price=self.MAX_PRICE,
        )

    def enrich(self, listings):
        return fetch_details(listings, self.city, city_paths=self.CITY_PATHS)


class ImovirtualBuyScraper(ImovirtualBaseScraper):
    CITY_PATHS = BUY_CITY_PATHS
    MIN_PRICE = config.MIN_PRICE
    MAX_PRICE = config.MAX_PRICE


class ImovirtualRentalScraper(ImovirtualBaseScraper):
    CITY_PATHS = RENTAL_CITY_PATHS
    MIN_PRICE = config.MIN_RENTAL_PRICE
    MAX_PRICE = config.MAX_RENTAL_PRICE


# Backward-compatible alias
ImovirtualScraper = ImovirtualBuyScraper
