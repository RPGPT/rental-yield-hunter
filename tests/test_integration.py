from unittest.mock import MagicMock, patch

from db.models import Listing, ListingPriceHistory, RawData
from db.repository import upsert_listings
from scraper.imovirtual.fetcher import fetch_details
from scraper.imovirtual.parser import parse
from tests.conftest import make_item

BUILD_ID_HTML = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"test-build-123"}</script>'
CITY = "Porto"


def _page(items, total_pages=1, page=1):
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


class TestFullPipeline:
    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_scrape_stores_listings_in_db(self, mock_time, mock_curl, clean_db):
        items = [
            make_item(
                id=1001,
                href="[lang]/ad/apt-a-ID1001",
                title="Apt A",
                totalPrice={"value": 195000},
                estate="FLAT",
                roomsNumber="TWO",
                shortDescription="Arrendado com inquilino",
            ),
            make_item(
                id=1002,
                href="[lang]/ad/apt-b-ID1002",
                title="Apt B",
                totalPrice={"value": 250000},
                estate="HOUSE",
                roomsNumber="THREE",
                tags=["PARKING_SPOT"],
                shortDescription="Vista mar, bom estado",
            ),
        ]
        session = MagicMock()
        mock_curl.Session.return_value = session
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _page(items)
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_resp]

        from scraper.imovirtual.fetcher import fetch

        upsert_listings(clean_db, parse(fetch(CITY), CITY))

        rows = clean_db.query(Listing).order_by(Listing.id).all()
        assert len(rows) == 2

        apt_a = clean_db.query(Listing).filter(Listing.id == "1001").first()
        assert apt_a.title == "Apt A"
        assert apt_a.price == 195000
        assert apt_a.property_type == "apartment"
        assert apt_a.typology == "T1"  # roomsNumber=TWO → 2 divisions = T1
        assert apt_a.source == "imovirtual"

        apt_b = clean_db.query(Listing).filter(Listing.id == "1002").first()
        assert apt_b.price == 250000
        assert apt_b.property_type == "house"
        assert apt_b.typology == "T2"  # roomsNumber=THREE → 3 divisions = T2
        assert apt_b.has_garage is True
        assert apt_b.is_rented is False

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_rescrape_updates_price_and_tracks_history(self, mock_time, mock_curl, clean_db):
        session = MagicMock()
        mock_curl.Session.return_value = session

        api_v1 = MagicMock(status_code=200)
        api_v1.json.return_value = _page([make_item(id=2001, href="[lang]/ad/x-ID2001", totalPrice={"value": 200000})])
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_v1]

        from scraper.imovirtual.fetcher import fetch

        upsert_listings(clean_db, parse(fetch(CITY), CITY))
        assert clean_db.query(Listing).filter(Listing.id == "2001").first().price == 200000

        api_v2 = MagicMock(status_code=200)
        api_v2.json.return_value = _page([make_item(id=2001, href="[lang]/ad/x-ID2001", totalPrice={"value": 185000})])
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_v2]

        upsert_listings(clean_db, parse(fetch(CITY), CITY))
        clean_db.expire_all()

        assert clean_db.query(Listing).filter(Listing.id == "2001").first().price == 185000
        history = clean_db.query(ListingPriceHistory).filter(ListingPriceHistory.listing_id == "2001").all()
        assert len(history) == 1
        assert history[0].price == 185000

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_raw_json_stored(self, mock_time, mock_curl, clean_db):
        session = MagicMock()
        mock_curl.Session.return_value = session
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _page([make_item(id=3001, href="[lang]/ad/z-ID3001")])
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_resp]

        from scraper.imovirtual.fetcher import fetch

        upsert_listings(clean_db, parse(fetch(CITY), CITY))

        raw = clean_db.query(RawData).filter(RawData.listing_id == "3001").first()
        assert raw is not None
        assert raw.raw_json["id"] == 3001

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_dedup_same_listing_different_pages(self, mock_time, mock_curl, clean_db):
        session = MagicMock()
        mock_curl.Session.return_value = session
        item = make_item(id=4001, href="[lang]/ad/dup-ID4001")
        page1 = MagicMock(status_code=200)
        page1.json.return_value = _page([item], total_pages=2, page=1)
        page2 = MagicMock(status_code=200)
        page2.json.return_value = _page([item], total_pages=2, page=2)
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), page1, page2]

        from scraper.imovirtual.fetcher import fetch

        upsert_listings(clean_db, parse(fetch(CITY), CITY))
        assert clean_db.query(Listing).filter(Listing.id == "4001").count() == 1

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_price_filter_excludes_expensive(self, mock_time, mock_curl, clean_db):
        session = MagicMock()
        mock_curl.Session.return_value = session
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _page(
            [
                make_item(id=5001, href="[lang]/ad/c-ID5001", totalPrice={"value": 200000}),
                make_item(id=5002, href="[lang]/ad/e-ID5002", totalPrice={"value": 900000}),
            ]
        )
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_resp]

        from scraper.imovirtual.fetcher import fetch

        upsert_listings(clean_db, parse(fetch(CITY), CITY))
        assert clean_db.query(Listing).filter(Listing.id == "5001").count() == 1
        assert clean_db.query(Listing).filter(Listing.id == "5002").count() == 0

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_first_seen_preserved_across_runs(self, mock_time, mock_curl, clean_db):
        session = MagicMock()
        mock_curl.Session.return_value = session
        item = make_item(id=6001, href="[lang]/ad/fs-ID6001")

        api1 = MagicMock(status_code=200)
        api1.json.return_value = _page([item])
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api1]

        from scraper.imovirtual.fetcher import fetch

        upsert_listings(clean_db, parse(fetch(CITY), CITY))
        first_seen = clean_db.query(Listing).filter(Listing.id == "6001").first().first_seen

        api2 = MagicMock(status_code=200)
        api2.json.return_value = _page([item])
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api2]

        upsert_listings(clean_db, parse(fetch(CITY), CITY))
        clean_db.expire_all()

        assert clean_db.query(Listing).filter(Listing.id == "6001").first().first_seen == first_seen

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_lifetime_rent_via_enrich(self, mock_time, mock_curl, clean_db):
        session = MagicMock()
        mock_curl.Session.return_value = session
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _page(
            [
                make_item(
                    id=7001,
                    href="[lang]/ad/vit-ID7001",
                    title="Apartamento arrendado",
                    shortDescription="Com inquilino",
                )
            ]
        )
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_resp]

        from scraper.imovirtual.fetcher import fetch

        listings = parse(fetch(CITY), CITY)
        assert listings[0]["is_rented"] is True

        detail_session = MagicMock()
        mock_curl.Session.return_value = detail_session
        detail_resp = MagicMock(status_code=200)
        detail_resp.json.return_value = {
            "pageProps": {"ad": {"description": "Renda vitalicia garantida pelo contrato"}}
        }
        detail_session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail_resp]

        upsert_listings(clean_db, fetch_details(listings, CITY))

        row = clean_db.query(Listing).filter(Listing.id == "7001").first()
        assert row.is_rented is True
        assert row.lifetime_rent is True
        assert "vitalicia" in row.description.lower()

        raw = clean_db.query(RawData).filter(RawData.listing_id == "7001").first()
        assert raw.raw_json is not None
