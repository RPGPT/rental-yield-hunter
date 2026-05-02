from abc import ABC, abstractmethod


class Scraper(ABC):
    @abstractmethod
    def fetch(self) -> list[dict]:
        ...

    @abstractmethod
    def parse(self, responses: list[dict]) -> list[dict]:
        ...

    def run(self) -> list[dict]:
        return self.parse(self.fetch())

