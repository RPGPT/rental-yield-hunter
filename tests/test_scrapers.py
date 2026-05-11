from unittest.mock import MagicMock, patch

import pytest

import config
from scraper.base import Scraper
from scraper.imovirtual import ImovirtualBuyScraper, ImovirtualRentalScraper, ImovirtualScraper
from scraper.imovirtual.constants import BUY_CITY_PATHS, RENTAL_CITY_PATHS


class TestImovirtualBuyScraper:
    def test_is_scraper_subclass(self):
        assert issubclass(ImovirtualBuyScraper, Scraper)

    def test_city_paths(self):
        assert ImovirtualBuyScraper.CITY_PATHS is BUY_CITY_PATHS

    def test_price_bounds(self):
        assert ImovirtualBuyScraper.MIN_PRICE == config.MIN_PRICE
        assert ImovirtualBuyScraper.MAX_PRICE == config.MAX_PRICE

    def test_buy_paths_use_comprar(self):
        for search_path, api_path in BUY_CITY_PATHS.values():
            assert "comprar" in search_path
            assert "comprar" in api_path


class TestImovirtualRentalScraper:
    def test_is_scraper_subclass(self):
        assert issubclass(ImovirtualRentalScraper, Scraper)

    def test_city_paths(self):
        assert ImovirtualRentalScraper.CITY_PATHS is RENTAL_CITY_PATHS

    def test_price_bounds(self):
        assert ImovirtualRentalScraper.MIN_PRICE == config.MIN_RENTAL_PRICE
        assert ImovirtualRentalScraper.MAX_PRICE == config.MAX_RENTAL_PRICE

    def test_rental_paths_use_arrendar(self):
        for search_path, api_path in RENTAL_CITY_PATHS.values():
            assert "arrendar" in search_path
            assert "arrendar" in api_path

    def test_same_cities_as_buy(self):
        assert set(RENTAL_CITY_PATHS.keys()) == set(BUY_CITY_PATHS.keys())


class TestImovirtualScraperAlias:
    def test_is_buy_scraper(self):
        assert ImovirtualScraper is ImovirtualBuyScraper


class TestImovirtualBaseScraperRun:
    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_buy_scraper_run_returns_listings(self, mock_time, mock_curl):
        BUILD_ID_HTML = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"b1"}</script>'
        session = MagicMock()
        mock_curl.Session.return_value = session

        page = MagicMock(status_code=200)
        page.json.return_value = {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [
                            {
                                "id": 88001,
                                "href": "[lang]/ad/apt-ID88001",
                                "title": "T2 Porto",
                                "totalPrice": {"value": 200000},
                                "estate": "FLAT",
                                "roomsNumber": "TWO",
                                "areaInSquareMeters": 80,
                                "pricePerSquareMeter": {"value": 2500},
                                "tags": [],
                                "location": {
                                    "address": {"street": {}, "city": {}, "province": {"name": "Porto"}},
                                    "reverseGeocoding": {"locations": [{"locationLevel": "council", "name": "Porto"}]},
                                },
                            }
                        ],
                        "pagination": {"totalPages": 1, "totalItems": 1},
                    }
                }
            }
        }
        session.get.return_value = MagicMock(status_code=200, text=BUILD_ID_HTML)
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), page]

        scraper = ImovirtualBuyScraper("Porto")
        listings = scraper.run()

        assert len(listings) == 1
        assert listings[0]["id"] == "88001"
        assert listings[0]["price"] == 200000

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_rental_scraper_fetches_from_arrendar_path(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        session.get.return_value = MagicMock(status_code=403)

        scraper = ImovirtualRentalScraper("Porto")
        scraper.run()

        first_url = session.get.call_args_list[0][0][0]
        assert "arrendar" in first_url

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_rental_scraper_applies_rental_price_ceiling(self, mock_time, mock_curl):
        BUILD_ID_HTML = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"b1"}</script>'
        session = MagicMock()
        mock_curl.Session.return_value = session

        page = MagicMock(status_code=200)
        page.json.return_value = {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [{"totalPrice": {"value": config.MAX_RENTAL_PRICE + 1}}],
                        "pagination": {"totalPages": 5, "totalItems": 150},
                    }
                }
            }
        }
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), page]

        scraper = ImovirtualRentalScraper("Porto")
        responses = scraper.fetch()

        assert len(responses) == 1
        assert session.get.call_count == 2

    def test_rental_scraper_raises_for_unsupported_city(self):
        from scraper.imovirtual.fetcher import fetch

        with pytest.raises(ValueError, match="Unsupported city"):
            fetch("Lisboa", city_paths=RENTAL_CITY_PATHS)
