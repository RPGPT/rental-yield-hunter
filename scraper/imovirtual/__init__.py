from scraper.base import Scraper
from scraper.imovirtual.fetcher import fetch, fetch_details
from scraper.imovirtual.parser import parse


class ImovirtualScraper(Scraper):
    def __init__(self, city: str):
        self.city = city

    def fetch(self):
        return fetch(self.city)

    def parse(self, responses):
        return parse(responses, target_city=self.city)

    def enrich(self, listings):
        return fetch_details(listings, self.city)
