import json
from unittest.mock import MagicMock, patch

from scraper.imovirtual.fetcher import extract_next_data, fetch_details, min_price


def _detail_html(description="Some description"):
    ad = {"description": description}
    data = json.dumps({"pageProps": {"ad": ad}}, ensure_ascii=False)
    return f'<html><script id="__NEXT_DATA__" type="application/json">{data}</script></html>'


def _mock_session(mock_curl, *responses):
    session = MagicMock()
    mock_curl.Session.return_value = session
    if len(responses) == 1:
        session.get.return_value = responses[0]
    else:
        session.get.side_effect = list(responses)
    return session


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
        items = [{"totalPrice": {"value": 150000}}, {"totalPrice": {"value": 200000}}]
        assert min_price(items) == 150000

    def test_skips_none_price(self):
        items = [{"totalPrice": None}, {"totalPrice": {"value": 180000}}]
        assert min_price(items) == 180000

    def test_returns_none_for_empty(self):
        assert min_price([]) is None


def _build_id_html(build_id: str) -> str:
    return f'<script id="__NEXT_DATA__" type="application/json">{{"buildId":"{build_id}"}}</script>'


class TestFetchIntegration:
    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_stops_above_max_price(self, mock_time, mock_curl):
        html_resp = MagicMock(status_code=200, text=_build_id_html("test123"))
        page1_resp = MagicMock(status_code=200)
        page1_resp.json.return_value = {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [{"totalPrice": {"value": 500000}}],
                        "pagination": {"totalPages": 10, "totalItems": 300},
                    }
                }
            }
        }
        session = _mock_session(mock_curl, html_resp, page1_resp)

        from scraper.imovirtual.fetcher import fetch

        responses = fetch()

        assert len(responses) == 1
        assert session.get.call_count == 2

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_paginates_until_last_page(self, mock_time, mock_curl):
        html_resp = MagicMock(status_code=200, text=_build_id_html("b1"))

        def make_page(page_num, total_pages=2):
            resp = MagicMock(status_code=200)
            resp.json.return_value = {
                "pageProps": {
                    "data": {
                        "searchAds": {
                            "items": [{"totalPrice": {"value": 100000 + page_num * 1000}}],
                            "pagination": {"totalPages": total_pages, "totalItems": 70},
                        }
                    }
                }
            }
            return resp

        _mock_session(mock_curl, html_resp, make_page(1), make_page(2))

        from scraper.imovirtual.fetcher import fetch

        assert len(fetch()) == 2

    @patch("scraper.imovirtual.fetcher.curl_requests")
    def test_returns_empty_on_failed_build_id(self, mock_curl):
        _mock_session(mock_curl, MagicMock(status_code=403))

        from scraper.imovirtual.fetcher import fetch

        assert fetch() == []


class TestFetchDetails:
    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_sets_lifetime_rent_true(self, mock_time, mock_curl):
        _mock_session(mock_curl, MagicMock(status_code=200, text=_detail_html("Renda vital\u00edcia garantida")))
        result = fetch_details([{"url": "https://www.imovirtual.com/pt/anuncio/x", "title": "", "is_rented": False}])

        assert result[0]["lifetime_rent"] is True
        assert "vital" in result[0]["description"].lower()

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_sets_lifetime_rent_false_without_keyword(self, mock_time, mock_curl):
        _mock_session(mock_curl, MagicMock(status_code=200, text=_detail_html("Apartamento arrendado bom estado")))
        result = fetch_details([{"url": "https://www.imovirtual.com/pt/anuncio/y", "title": "", "is_rented": False}])

        assert result[0]["lifetime_rent"] is False

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_vitalicio_without_accent(self, mock_time, mock_curl):
        _mock_session(mock_curl, MagicMock(status_code=200, text=_detail_html("Contrato vitalicio em vigor")))
        result = fetch_details([{"url": "https://www.imovirtual.com/pt/anuncio/z", "title": "", "is_rented": False}])

        assert result[0]["lifetime_rent"] is True

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_case_insensitive(self, mock_time, mock_curl):
        _mock_session(mock_curl, MagicMock(status_code=200, text=_detail_html("RENDA VITAL\u00cdCIA")))
        result = fetch_details([{"url": "https://www.imovirtual.com/pt/anuncio/w", "title": "", "is_rented": False}])

        assert result[0]["lifetime_rent"] is True

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_fetches_all_listings(self, mock_time, mock_curl):
        session = _mock_session(mock_curl, MagicMock(status_code=200, text=_detail_html("Normal listing")))
        listings = [
            {"url": "https://www.imovirtual.com/pt/anuncio/a", "title": "", "is_rented": False},
            {"url": "https://www.imovirtual.com/pt/anuncio/b", "title": "", "is_rented": False},
        ]
        result = fetch_details(listings)

        assert session.get.call_count == 2
        assert "_raw_html" in result[0]
        assert "_raw_html" in result[1]

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_stores_raw_html(self, mock_time, mock_curl):
        html = _detail_html("Test")
        _mock_session(mock_curl, MagicMock(status_code=200, text=html))
        result = fetch_details([{"url": "https://www.imovirtual.com/pt/anuncio/q", "title": "", "is_rented": False}])

        assert result[0]["_raw_html"] == html

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_detail_error_no_crash(self, mock_time, mock_curl):
        _mock_session(mock_curl, MagicMock(status_code=404))
        result = fetch_details([{"url": "https://www.imovirtual.com/pt/anuncio/gone", "title": "", "is_rented": False}])

        assert "description" not in result[0] or result[0].get("description") is None
        assert "_raw_html" not in result[0]

    def test_empty_listings(self):
        assert fetch_details([]) == []

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_mixed_rented_and_not(self, mock_time, mock_curl):
        session = _mock_session(mock_curl, MagicMock(status_code=200, text=_detail_html("Arrendado vitalicio")))
        listings = [
            {"url": "https://www.imovirtual.com/pt/anuncio/a", "title": "", "is_rented": True},
            {"url": "https://www.imovirtual.com/pt/anuncio/b", "title": "", "is_rented": False},
        ]
        result = fetch_details(listings)

        assert result[0]["lifetime_rent"] is True
        assert result[0]["_raw_html"] is not None
        assert result[1]["_raw_html"] is not None
        assert session.get.call_count == 2
