import json
from unittest.mock import MagicMock, patch

import pytest

from scraper.imovirtual.fetcher import extract_next_data, fetch_details, min_price

BUILD_ID_HTML = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"b1"}</script>'
CITY = "Porto"


class TestExtractNextData:
    def test_extracts_build_id(self):
        html = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"abc123","props":{}}</script>'
        assert extract_next_data(html)["buildId"] == "abc123"

    def test_returns_none_when_missing(self):
        assert extract_next_data("<html><body></body></html>") is None

    def test_handles_complex_json(self):
        payload = {"buildId": "xyz", "props": {"pageProps": {"data": {}}}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
        assert extract_next_data(html)["buildId"] == "xyz"


class TestMinPrice:
    def test_returns_first_price(self):
        assert min_price([{"totalPrice": {"value": 150000}}, {"totalPrice": {"value": 200000}}]) == 150000

    def test_skips_none_price(self):
        assert min_price([{"totalPrice": None}, {"totalPrice": {"value": 180000}}]) == 180000

    def test_returns_none_for_empty(self):
        assert min_price([]) is None


class TestFetchIntegration:
    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_stops_above_max_price(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        page1 = MagicMock(status_code=200)
        page1.json.return_value = {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [{"totalPrice": {"value": 500000}}],
                        "pagination": {"totalPages": 10, "totalItems": 300},
                    }
                }
            }
        }
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), page1]

        from scraper.imovirtual.fetcher import fetch

        assert len(fetch(CITY)) == 1
        assert session.get.call_count == 2

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_paginates_until_last_page(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        page1 = MagicMock(status_code=200)
        page1.json.return_value = {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [{"totalPrice": {"value": 101000}}],
                        "pagination": {"totalPages": 2, "totalItems": 70},
                    }
                }
            }
        }
        page2 = MagicMock(status_code=200)
        page2.json.return_value = {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [{"totalPrice": {"value": 102000}}],
                        "pagination": {"totalPages": 2, "totalItems": 70},
                    }
                }
            }
        }
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), page1, page2]

        from scraper.imovirtual.fetcher import fetch

        assert len(fetch(CITY)) == 2

    @patch("scraper.imovirtual.fetcher.curl_requests")
    def test_returns_empty_on_failed_build_id(self, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        session.get.return_value = MagicMock(status_code=403)

        from scraper.imovirtual.fetcher import fetch

        assert fetch(CITY) == []

    def test_raises_on_unsupported_city(self):
        from scraper.imovirtual.fetcher import fetch

        with pytest.raises(ValueError, match="Unsupported city"):
            fetch("Lisboa")


class TestFetchDetails:
    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_sets_lifetime_rent_true(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "Renda vitalícia garantida"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        listing = [{"url": "https://www.imovirtual.com/pt/anuncio/x", "title": "", "is_rented": True}]
        result = fetch_details(listing, CITY)

        assert result[0]["lifetime_rent"] is True
        assert "vital" in result[0]["description"].lower()

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_sets_lifetime_rent_false_without_keyword(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "Apartamento arrendado bom estado"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        listing = [{"url": "https://www.imovirtual.com/pt/anuncio/y", "title": "", "is_rented": True}]
        result = fetch_details(listing, CITY)

        assert result[0]["lifetime_rent"] is False

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_vitalicio_without_accent(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "Contrato vitalicio em vigor"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        listing = [{"url": "https://www.imovirtual.com/pt/anuncio/z", "title": "", "is_rented": True}]
        result = fetch_details(listing, CITY)

        assert result[0]["lifetime_rent"] is True

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_case_insensitive(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "RENDA VITALÍCIA"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        listing = [{"url": "https://www.imovirtual.com/pt/anuncio/w", "title": "", "is_rented": True}]
        result = fetch_details(listing, CITY)

        assert result[0]["lifetime_rent"] is True

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_skips_non_rented_listings(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session

        fetch_details(
            [
                {"url": "https://www.imovirtual.com/pt/anuncio/a", "title": "", "is_rented": False},
                {"url": "https://www.imovirtual.com/pt/anuncio/b", "title": "", "is_rented": False},
            ],
            CITY,
        )

        assert session.get.call_count == 0

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_detail_error_falls_back_to_short_description(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), MagicMock(status_code=404)]

        result = fetch_details(
            [
                {
                    "url": "https://www.imovirtual.com/pt/anuncio/gone",
                    "title": "",
                    "description": "Apartamento arrendado",
                    "is_rented": True,
                }
            ],
            CITY,
        )

        assert result[0]["description"] == "Apartamento arrendado"

    def test_empty_listings(self):
        assert fetch_details([], CITY) == []

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_only_rented_fetched_in_mixed_list(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "Arrendado vitalicio"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        result = fetch_details(
            [
                {"url": "https://www.imovirtual.com/pt/anuncio/a", "title": "", "is_rented": True},
                {"url": "https://www.imovirtual.com/pt/anuncio/b", "title": "", "is_rented": False},
            ],
            CITY,
        )

        assert session.get.call_count == 2
        assert result[0]["lifetime_rent"] is True

    def test_raises_on_unsupported_city(self):
        with pytest.raises(ValueError, match="Unsupported city"):
            fetch_details([{"url": "https://x.com", "is_rented": True}], "Lisboa")


_RENTAL_PATHS = {
    "Porto": (
        "arrendar/apartamento/porto/",
        "pt/resultados/arrendar/apartamento/porto/porto.json",
    ),
}


class TestFetchCustomCityPaths:
    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_fetch_uses_custom_city_paths(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        page = MagicMock(status_code=200)
        page.json.return_value = {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [{"totalPrice": {"value": 1200}}],
                        "pagination": {"totalPages": 1, "totalItems": 1},
                    }
                }
            }
        }
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), page]

        from scraper.imovirtual.fetcher import fetch

        result = fetch("Porto", city_paths=_RENTAL_PATHS)

        assert len(result) == 1
        first_call_url = session.get.call_args_list[0][0][0]
        assert "arrendar" in first_call_url

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_fetch_raises_for_city_not_in_custom_paths(self, mock_time, mock_curl):
        from scraper.imovirtual.fetcher import fetch

        with pytest.raises(ValueError, match="Unsupported city"):
            fetch("Maia", city_paths=_RENTAL_PATHS)

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_fetch_respects_custom_max_price(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        page = MagicMock(status_code=200)
        page.json.return_value = {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [{"totalPrice": {"value": 5000}}],
                        "pagination": {"totalPages": 5, "totalItems": 150},
                    }
                }
            }
        }
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), page]

        from scraper.imovirtual.fetcher import fetch

        result = fetch(CITY, max_price=4000)
        assert len(result) == 1
        assert session.get.call_count == 2

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_fetch_details_uses_custom_city_paths(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "Apartamento arrendado"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        from scraper.imovirtual.fetcher import fetch_details

        fetch_details(
            [{"url": "https://www.imovirtual.com/pt/anuncio/x", "title": "", "is_rented": True}],
            "Porto",
            city_paths=_RENTAL_PATHS,
        )

        first_call_url = session.get.call_args_list[0][0][0]
        assert "arrendar" in first_call_url

    def test_fetch_details_raises_for_city_not_in_custom_paths(self):
        from scraper.imovirtual.fetcher import fetch_details

        with pytest.raises(ValueError, match="Unsupported city"):
            fetch_details(
                [{"url": "https://x.com", "is_rented": True}],
                "Maia",
                city_paths=_RENTAL_PATHS,
            )

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_lifetime_rent_detected_in_full_description_only(self, mock_time, mock_curl):
        """Regression: vitalícia appears in fullDescription but not in description."""
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {
            "pageProps": {
                "ad": {
                    "description": "Apartamento arrendado em zona premium.",
                    "fullDescription": (
                        "Atualmente arrendado com contrato de inquilina vitalícia (renda atual de 162,90\u20ac/m\xeas)."
                    ),
                }
            }
        }
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        listing = [{"url": "https://www.imovirtual.com/pt/anuncio/v", "title": "", "is_rented": True}]
        result = fetch_details(listing, CITY)

        assert result[0]["lifetime_rent"] is True
        # description field stores only the short description, not fullDescription
        assert result[0]["description"] == "Apartamento arrendado em zona premium."
