"""Registry mapping ``(source, listing_type)`` to concrete scraper classes."""

from __future__ import annotations

from yieldhunter.sources.base import Scraper
from yieldhunter.sources.casasapo import CasaSapoBuyScraper, CasaSapoRentalScraper
from yieldhunter.sources.era import ERABuyScraper, ERARentalScraper
from yieldhunter.sources.imovirtual import ImovirtualBuyScraper, ImovirtualRentalScraper

SCRAPERS: dict[str, dict[str, type[Scraper]]] = {
    "imovirtual": {
        "buy": ImovirtualBuyScraper,
        "rent": ImovirtualRentalScraper,
    },
    "era": {
        "buy": ERABuyScraper,
        "rent": ERARentalScraper,
    },
    "casasapo": {
        "buy": CasaSapoBuyScraper,
        "rent": CasaSapoRentalScraper,
    },
}


def get_scraper_class(source: str, listing_type: str) -> type[Scraper]:
    source_scrapers = SCRAPERS.get(source)
    if not source_scrapers:
        raise ValueError(f"Unknown source: {source!r} (available: {', '.join(SCRAPERS)})")

    scraper_cls = source_scrapers.get(listing_type)
    if not scraper_cls:
        raise ValueError(f"Unknown listing type: {listing_type!r} (available: buy, rent)")

    return scraper_cls


def create_scraper(source: str, listing_type: str, city: str) -> Scraper:
    cls = get_scraper_class(source, listing_type)
    return cls(city)
