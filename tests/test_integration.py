from unittest.mock import MagicMock, patch
import json

from db.models import Listing, ListingPriceHistory, RawData
from db.repository import upsert_listings
from scraper.imovirtual.parser import parse
from scraper.imovirtual.fetcher import fetch_details
from tests.conftest import make_item


def _fake_api_page(items, total_pages=1, page=1):
    return {
        "pageProps": {
            "data": {
                "searchAds": {
                    "items": items,
                    "pagination": {
                        "totalItems": len(items) * total_pages,
                        "totalPages": total_pages,
                        "currentPage": page,
                    },
                }
            }
        }
    }


def _html_with_build_id(build_id="test-build-123"):
    return f'<script id="__NEXT_DATA__" type="application/json">{{"buildId":"{build_id}"}}</script>'


class TestFullPipeline:

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_scrape_stores_listings_in_db(self, mock_time, mock_curl, clean_db):
        items = [
            make_item(id=1001, href="[lang]/ad/apt-a-ID1001", title="Apt A",
                      totalPrice={"value": 195000}, estate="FLAT", roomsNumber="TWO",
                      shortDescription="Arrendado com inquilino"),
            make_item(id=1002, href="[lang]/ad/apt-b-ID1002", title="Apt B",
                      totalPrice={"value": 250000}, estate="HOUSE", roomsNumber="THREE",
                      tags=["PARKING_SPOT"],
                      shortDescription="Vista mar, bom estado"),
        ]

        session = MagicMock()
        mock_curl.Session.return_value = session

        html_resp = MagicMock(status_code=200, text=_html_with_build_id())
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _fake_api_page(items)
        session.get.side_effect = [html_resp, api_resp]

        from scraper.imovirtual.fetcher import fetch
        responses = fetch()
        listings = parse(responses)
        upsert_listings(clean_db, listings)

        rows = clean_db.query(Listing).order_by(Listing.id).all()
        assert len(rows) == 2

        apt_a = clean_db.query(Listing).filter(Listing.id == "1001").first()
        assert apt_a.title == "Apt A"
        assert apt_a.price == 195000
        assert apt_a.property_type == "apartment"
        assert apt_a.typology == "T2"
        assert apt_a.source == "imovirtual"

        apt_b = clean_db.query(Listing).filter(Listing.id == "1002").first()
        assert apt_b.price == 250000
        assert apt_b.property_type == "house"
        assert apt_b.typology == "T3"
        assert apt_b.has_garage is True
        assert apt_b.is_rented is False

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_rescrape_updates_price_and_tracks_history(self, mock_time, mock_curl, clean_db):
        item_v1 = make_item(id=2001, href="[lang]/ad/x-ID2001", totalPrice={"value": 200000})
        item_v2 = make_item(id=2001, href="[lang]/ad/x-ID2001", totalPrice={"value": 185000})

        session = MagicMock()
        mock_curl.Session.return_value = session

        html_resp = MagicMock(status_code=200, text=_html_with_build_id())

        # Day 1
        api_v1 = MagicMock(status_code=200)
        api_v1.json.return_value = _fake_api_page([item_v1])
        session.get.side_effect = [html_resp, api_v1]

        from scraper.imovirtual.fetcher import fetch
        upsert_listings(clean_db, parse(fetch()))

        row = clean_db.query(Listing).filter(Listing.id == "2001").first()
        assert row.price == 200000

        # Day 2 — price dropped
        api_v2 = MagicMock(status_code=200)
        api_v2.json.return_value = _fake_api_page([item_v2])
        session.get.side_effect = [html_resp, api_v2]

        upsert_listings(clean_db, parse(fetch()))

        clean_db.expire_all()
        row = clean_db.query(Listing).filter(Listing.id == "2001").first()
        assert row.price == 185000

        history = clean_db.query(ListingPriceHistory).filter(
            ListingPriceHistory.listing_id == "2001"
        ).all()
        assert len(history) == 1
        assert history[0].price == 185000

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_raw_json_stored(self, mock_time, mock_curl, clean_db):
        item = make_item(id=3001, href="[lang]/ad/z-ID3001")

        session = MagicMock()
        mock_curl.Session.return_value = session

        html_resp = MagicMock(status_code=200, text=_html_with_build_id())
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _fake_api_page([item])
        session.get.side_effect = [html_resp, api_resp]

        from scraper.imovirtual.fetcher import fetch
        upsert_listings(clean_db, parse(fetch()))

        raw = clean_db.query(RawData).filter(RawData.listing_id == "3001").first()
        assert raw is not None
        assert raw.raw_json["id"] == 3001

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_dedup_same_listing_different_pages(self, mock_time, mock_curl, clean_db):
        item = make_item(id=4001, href="[lang]/ad/dup-ID4001")

        session = MagicMock()
        mock_curl.Session.return_value = session

        html_resp = MagicMock(status_code=200, text=_html_with_build_id())

        page1 = MagicMock(status_code=200)
        page1.json.return_value = _fake_api_page([item], total_pages=2, page=1)
        page2 = MagicMock(status_code=200)
        page2.json.return_value = _fake_api_page([item], total_pages=2, page=2)

        session.get.side_effect = [html_resp, page1, page2]

        from scraper.imovirtual.fetcher import fetch
        listings = parse(fetch())
        upsert_listings(clean_db, listings)

        count = clean_db.query(Listing).filter(Listing.id == "4001").count()
        assert count == 1

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_price_filter_excludes_expensive(self, mock_time, mock_curl, clean_db):
        cheap = make_item(id=5001, href="[lang]/ad/c-ID5001", totalPrice={"value": 200000})
        expensive = make_item(id=5002, href="[lang]/ad/e-ID5002", totalPrice={"value": 900000})

        session = MagicMock()
        mock_curl.Session.return_value = session

        html_resp = MagicMock(status_code=200, text=_html_with_build_id())
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _fake_api_page([cheap, expensive])
        session.get.side_effect = [html_resp, api_resp]

        from scraper.imovirtual.fetcher import fetch
        listings = parse(fetch())
        upsert_listings(clean_db, listings)

        assert clean_db.query(Listing).filter(Listing.id == "5001").count() == 1
        assert clean_db.query(Listing).filter(Listing.id == "5002").count() == 0

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_first_seen_preserved_across_runs(self, mock_time, mock_curl, clean_db):
        item = make_item(id=6001, href="[lang]/ad/fs-ID6001")

        session = MagicMock()
        mock_curl.Session.return_value = session
        html_resp = MagicMock(status_code=200, text=_html_with_build_id())

        # Run 1
        api1 = MagicMock(status_code=200)
        api1.json.return_value = _fake_api_page([item])
        session.get.side_effect = [html_resp, api1]

        from scraper.imovirtual.fetcher import fetch
        upsert_listings(clean_db, parse(fetch()))
        first_seen = clean_db.query(Listing).filter(Listing.id == "6001").first().first_seen

        # Run 2
        api2 = MagicMock(status_code=200)
        api2.json.return_value = _fake_api_page([item])
        session.get.side_effect = [html_resp, api2]

        upsert_listings(clean_db, parse(fetch()))
        clean_db.expire_all()

        assert clean_db.query(Listing).filter(Listing.id == "6001").first().first_seen == first_seen

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_lifetime_rent_via_enrich(self, mock_time, mock_curl, clean_db):
        item = make_item(
            id=7001, href="[lang]/ad/vit-ID7001",
            title="Apartamento arrendado",
            shortDescription="Com inquilino",
        )

        session = MagicMock()
        mock_curl.Session.return_value = session

        html_resp = MagicMock(status_code=200, text=_html_with_build_id())
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _fake_api_page([item])
        session.get.side_effect = [html_resp, api_resp]

        from scraper.imovirtual.fetcher import fetch
        listings = parse(fetch())
        assert listings[0]["is_rented"] is True

        ad = {"description": "Renda vitalicia garantida pelo contrato"}
        detail_data = json.dumps({"pageProps": {"ad": ad}}, ensure_ascii=False)
        detail_html = f'<html><script id="__NEXT_DATA__" type="application/json">{detail_data}</script></html>'

        detail_session = MagicMock()
        detail_resp = MagicMock(status_code=200, text=detail_html)
        detail_session.get.return_value = detail_resp
        mock_curl.Session.return_value = detail_session

        enriched = fetch_details(listings)
        upsert_listings(clean_db, enriched)

        row = clean_db.query(Listing).filter(Listing.id == "7001").first()
        assert row.is_rented is True
        assert row.lifetime_rent is True
        assert "vitalicia" in row.description.lower()

        raw = clean_db.query(RawData).filter(RawData.listing_id == "7001").first()
        assert raw.raw_html is not None
        assert raw.raw_json is not None

