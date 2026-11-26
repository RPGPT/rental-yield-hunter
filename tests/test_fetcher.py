import json
from unittest.mock import MagicMock, patch

import pytest

from yieldhunter.sources.imovirtual.client import extract_next_data, fetch_details, min_price

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
    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
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

        from yieldhunter.sources.imovirtual.client import fetch

        assert len(fetch(CITY)) == 1
        assert session.get.call_count == 2

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
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

        from yieldhunter.sources.imovirtual.client import fetch

        assert len(fetch(CITY)) == 2

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    def test_returns_empty_on_failed_build_id(self, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        session.get.return_value = MagicMock(status_code=403)

        from yieldhunter.sources.imovirtual.client import fetch

        assert fetch(CITY) == []

    def test_raises_on_unsupported_city(self):
        from yieldhunter.sources.imovirtual.client import fetch

        with pytest.raises(ValueError, match="Unsupported city"):
            fetch("Lisboa")


class TestFetchDetails:
    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
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

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
    def test_sets_lifetime_rent_false_without_keyword(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "Apartamento arrendado bom estado"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        listing = [{"url": "https://www.imovirtual.com/pt/anuncio/y", "title": "", "is_rented": True}]
        result = fetch_details(listing, CITY)

        assert result[0]["lifetime_rent"] is False

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
    def test_vitalicio_without_accent(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "Contrato vitalicio em vigor"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        listing = [{"url": "https://www.imovirtual.com/pt/anuncio/z", "title": "", "is_rented": True}]
        result = fetch_details(listing, CITY)

        assert result[0]["lifetime_rent"] is True

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
    def test_case_insensitive(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "RENDA VITALÍCIA"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        listing = [{"url": "https://www.imovirtual.com/pt/anuncio/w", "title": "", "is_rented": True}]
        result = fetch_details(listing, CITY)

        assert result[0]["lifetime_rent"] is True

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
    def test_fetches_non_rented_listings_to_discover_full_description_rent(self, mock_time, mock_curl):
        from yieldhunter.sources.imovirtual.client import _detail_scan_bucket

        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {
            "pageProps": {
                "ad": {
                    "description": "Atualmente arrendado por 280 €/mês (contrato até 2032)",
                }
            }
        }
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        with patch(
            "yieldhunter.sources.imovirtual.client._current_detail_scan_bucket",
            return_value=_detail_scan_bucket("a"),
        ):
            result = fetch_details(
                [
                    {
                        "id": "a",
                        "url": "https://www.imovirtual.com/pt/anuncio/a",
                        "title": "",
                        "is_rented": False,
                    },
                ],
                CITY,
            )

        assert result[0]["is_rented"] is True
        assert session.get.call_count == 2

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
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
        assert result[0]["is_rented"] is True

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
    def test_empty_detail_description_preserves_short_description(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        result = fetch_details(
            [
                {
                    "url": "https://www.imovirtual.com/pt/anuncio/empty",
                    "title": "",
                    "description": "Apartamento arrendado por 280 euros",
                    "is_rented": True,
                }
            ],
            CITY,
        )

        assert result[0]["description"] == "Apartamento arrendado por 280 euros"
        assert result[0]["is_rented"] is True

    def test_empty_listings(self):
        assert fetch_details([], CITY) == []

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
    def test_fetches_rented_and_rotating_unflagged_listings(self, mock_time, mock_curl):
        from yieldhunter.sources.imovirtual.client import _detail_scan_bucket

        rented_id = "always-rented"
        rotating_id = next(str(i) for i in range(100) if _detail_scan_bucket(str(i)) != _detail_scan_bucket(rented_id))
        session = MagicMock()
        mock_curl.Session.return_value = session
        rented_detail = MagicMock(status_code=200)
        rented_detail.json.return_value = {"pageProps": {"ad": {"description": "Arrendado vitalicio"}}}
        other_detail = MagicMock(status_code=200)
        other_detail.json.return_value = {"pageProps": {"ad": {"description": "Apartamento disponível"}}}
        session.get.side_effect = [
            MagicMock(status_code=200, text=BUILD_ID_HTML),
            rented_detail,
            other_detail,
        ]

        with patch(
            "yieldhunter.sources.imovirtual.client._current_detail_scan_bucket",
            return_value=_detail_scan_bucket(rotating_id),
        ):
            result = fetch_details(
                [
                    {
                        "id": rented_id,
                        "url": "https://www.imovirtual.com/pt/anuncio/a",
                        "title": "",
                        "is_rented": True,
                    },
                    {
                        "id": rotating_id,
                        "url": "https://www.imovirtual.com/pt/anuncio/b",
                        "title": "",
                        "is_rented": False,
                    },
                ],
                CITY,
            )

        assert session.get.call_count == 3
        assert result[0]["lifetime_rent"] is True
        assert result[1]["is_rented"] is False

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
    def test_always_refreshes_previously_rented_listings(self, mock_time, mock_curl):
        from yieldhunter.sources.imovirtual.client import DETAIL_SCAN_BUCKETS, _detail_scan_bucket

        listing_id = "previously-rented"
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "Apartamento disponível"}}}
        session = MagicMock()
        mock_curl.Session.return_value = session
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        listing = {
            "id": listing_id,
            "url": "https://www.imovirtual.com/pt/anuncio/previous",
            "title": "",
            "is_rented": False,
        }
        with patch(
            "yieldhunter.sources.imovirtual.client._current_detail_scan_bucket",
            return_value=(_detail_scan_bucket(listing_id) + 1) % DETAIL_SCAN_BUCKETS,
        ):
            result = fetch_details([listing], CITY, known_rented_ids={listing_id})

        assert session.get.call_count == 2
        assert result[0]["is_rented"] is False

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    def test_skips_unflagged_listings_outside_current_scan_bucket(self, mock_curl):
        from yieldhunter.sources.imovirtual.client import DETAIL_SCAN_BUCKETS, _detail_scan_bucket

        listing_id = "not-in-todays-bucket"
        scan_bucket = (_detail_scan_bucket(listing_id) + 1) % DETAIL_SCAN_BUCKETS
        listings = [
            {
                "id": listing_id,
                "url": "https://www.imovirtual.com/pt/anuncio/unscanned",
                "title": "",
                "is_rented": False,
            }
        ]

        with patch(
            "yieldhunter.sources.imovirtual.client._current_detail_scan_bucket",
            return_value=scan_bucket,
        ):
            result = fetch_details(listings, CITY)

        assert result is listings
        mock_curl.Session.assert_not_called()

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
    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
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

        from yieldhunter.sources.imovirtual.client import fetch

        result = fetch("Porto", city_paths=_RENTAL_PATHS)

        assert len(result) == 1
        first_call_url = session.get.call_args_list[0][0][0]
        assert "arrendar" in first_call_url

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
    def test_fetch_raises_for_city_not_in_custom_paths(self, mock_time, mock_curl):
        from yieldhunter.sources.imovirtual.client import fetch

        with pytest.raises(ValueError, match="Unsupported city"):
            fetch("Maia", city_paths=_RENTAL_PATHS)

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
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

        from yieldhunter.sources.imovirtual.client import fetch

        result = fetch(CITY, max_price=4000)
        assert len(result) == 1
        assert session.get.call_count == 2

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
    def test_fetch_details_uses_custom_city_paths(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        detail = MagicMock(status_code=200)
        detail.json.return_value = {"pageProps": {"ad": {"description": "Apartamento arrendado"}}}
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail]

        from yieldhunter.sources.imovirtual.client import fetch_details

        fetch_details(
            [{"url": "https://www.imovirtual.com/pt/anuncio/x", "title": "", "is_rented": True}],
            "Porto",
            city_paths=_RENTAL_PATHS,
        )

        first_call_url = session.get.call_args_list[0][0][0]
        assert "arrendar" in first_call_url

    def test_fetch_details_raises_for_city_not_in_custom_paths(self):
        from yieldhunter.sources.imovirtual.client import fetch_details

        with pytest.raises(ValueError, match="Unsupported city"):
            fetch_details(
                [{"url": "https://x.com", "is_rented": True}],
                "Maia",
                city_paths=_RENTAL_PATHS,
            )

    @patch("yieldhunter.sources.imovirtual.client.curl_requests")
    @patch("yieldhunter.sources.imovirtual.client.time")
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
