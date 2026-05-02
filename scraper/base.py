from abc import ABC, abstractmethod
from typing import List


class Scraper(ABC):
    @abstractmethod
    def fetch(self) -> List[dict]:
        """Fetch raw API/HTML responses from the source."""

    @abstractmethod
    def parse(self, responses: List[dict]) -> List[dict]:
        """Parse raw responses into normalised listing dicts."""

    def run(self) -> List[dict]:
        return self.parse(self.fetch())

