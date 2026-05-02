import json
from unittest.mock import MagicMock, patch

from scraper.imovirtual.fetcher import extract_next_data, min_price


class TestExtractNextData:
    def test_extracts_build_id(self):
        html = '''
        <html><body>
        <script id="__NEXT_DATA__" type="application/json">{"buildId":"abc123","props":{}}</script>
        </body></html>
        '''
        data = extract_next_data(html)
        assert data["buildId"] == "abc123"

    def test_returns_none_when_missing(self):
        assert extract_next_data("<html><body></body></html>") is None

    def test_handles_complex_json(self):
        payload = {"buildId": "xyz", "props": {"pageProps": {"data": {}}}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
        data = extract_next_data(html)
        assert data["buildId"] == "xyz"


class TestMinPrice:
    def test_returns_first_price(self):
        items = [
            {"totalPrice": {"value": 150000}},
            {"totalPrice": {"value": 200000}},
        ]
        assert min_price(items) == 150000

    def test_skips_none_price(self):
        items = [
            {"totalPrice": None},
            {"totalPrice": {"value": 180000}},
        ]
        assert min_price(items) == 180000

    def test_returns_none_for_empty(self):
        assert min_price([]) is None


class TestFetchIntegration:
    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_stops_above_max_price(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session

        html_resp = MagicMock()
        html_resp.status_code = 200
        html_resp.text = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"test123"}</script>'

        page1_resp = MagicMock()
        page1_resp.status_code = 200
        page1_resp.json.return_value = {
            "pageProps": {"data": {"searchAds": {
                "items": [{"totalPrice": {"value": 500000}}],
                "pagination": {"totalPages": 10, "totalItems": 300},
            }}}
        }

        session.get.side_effect = [html_resp, page1_resp]

        from scraper.imovirtual.fetcher import fetch
        responses = fetch()

        assert len(responses) == 1
        assert session.get.call_count == 2

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_paginates_until_last_page(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session

        html_resp = MagicMock()
        html_resp.status_code = 200
        html_resp.text = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"b1"}</script>'

        def make_page(page_num, total_pages=2):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "pageProps": {"data": {"searchAds": {
                    "items": [{"totalPrice": {"value": 100000 + page_num * 1000}}],
                    "pagination": {"totalPages": total_pages, "totalItems": 70},
                }}}
            }
            return resp

        session.get.side_effect = [html_resp, make_page(1), make_page(2)]

        from scraper.imovirtual.fetcher import fetch
        responses = fetch()

        assert len(responses) == 2

    @patch("scraper.imovirtual.fetcher.curl_requests")
    def test_returns_empty_on_failed_build_id(self, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session

        resp = MagicMock()
        resp.status_code = 403
        session.get.return_value = resp

        from scraper.imovirtual.fetcher import fetch
        assert fetch() == []

