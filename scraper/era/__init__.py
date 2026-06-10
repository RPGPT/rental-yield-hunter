import config
from scraper.base import Scraper
from scraper.era.constants import BUSINESS_TYPE_BUY, BUSINESS_TYPE_RENT, CITY_CONFIG
from scraper.era.fetcher import fetch
from scraper.era.parser import parse


class ERABaseScraper(Scraper):
    CITY_CONFIG = CITY_CONFIG
    MIN_PRICE: int = 0
    MAX_PRICE: int = 0
    BUSINESS_TYPE_ID: int = BUSINESS_TYPE_BUY

    def __init__(self, city: str):
        self.city = city

    def fetch(self):
        return fetch(self.city, self.CITY_CONFIG, self.BUSINESS_TYPE_ID, max_price=self.MAX_PRICE)

    def parse(self, responses):
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


class ERARentalScraper(ERABaseScraper):
    MIN_PRICE = config.MIN_RENTAL_PRICE
    MAX_PRICE = config.MAX_RENTAL_PRICE
    BUSINESS_TYPE_ID = BUSINESS_TYPE_RENT
