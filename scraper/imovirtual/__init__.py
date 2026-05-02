from scraper.base import Scraper
from scraper.imovirtual.fetcher import fetch
from scraper.imovirtual.parser import parse


class ImovirtualScraper(Scraper):
    def fetch(self):
        return fetch()

    def parse(self, responses):
        return parse(responses)

