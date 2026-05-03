from abc import ABC, abstractmethod


class Scraper(ABC):
    @abstractmethod
    def fetch(self) -> list[dict]:
        ...

    @abstractmethod
    def parse(self, responses: list[dict]) -> list[dict]:
        ...

    def enrich(self, listings: list[dict]) -> list[dict]:
        return listings

    def run(self) -> list[dict]:
        responses = self.fetch()
        listings = self.parse(responses)
        return self.enrich(listings)
