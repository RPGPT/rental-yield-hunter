"""Base scraper contract and structured scrape outcome."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ScrapeResult:
    """Result of a scraper run, tracking whether pagination completed without HTTP errors."""

    listings: list[dict]
    complete: bool = True


class Scraper(ABC):
    last_fetch_complete: bool = True

    @abstractmethod
    def fetch(self) -> list[dict]: ...

    @abstractmethod
    def parse(self, responses: list[dict]) -> list[dict]: ...

    def enrich(self, listings: list[dict]) -> list[dict]:
        return listings

    def run(self) -> list[dict]:
        self.last_fetch_complete = True
        responses = self.fetch()
        listings = self.parse(responses)
        return self.enrich(listings)

    def run_checked(self) -> ScrapeResult:
        listings = self.run()
        return ScrapeResult(listings=listings, complete=self.last_fetch_complete)
