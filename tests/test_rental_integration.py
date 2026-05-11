from unittest.mock import MagicMock, patch

from db.models import RentalListing, RentalListingPriceHistory, RentalRawData
from db.repository import deactivate_missing_rentals, upsert_rental_listings
from scraper.imovirtual.constants import RENTAL_CITY_PATHS
from scraper.imovirtual.fetcher import fetch, fetch_details
from scraper.imovirtual.parser import parse
from tests.conftest import make_item

BUILD_ID_HTML = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"test-build-rental"}</script>'
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


class TestRentalFullPipeline:
    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_scrape_stores_rental_listings(self, mock_time, mock_curl, clean_rental_db):
        items = [
            make_item(id=9001, href="[lang]/ad/rent-a-ID9001", title="Rent A", totalPrice={"value": 1200}),
            make_item(id=9002, href="[lang]/ad/rent-b-ID9002", title="Rent B", totalPrice={"value": 1800}),
        ]
        session = MagicMock()
        mock_curl.Session.return_value = session
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _page(items)
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_resp]

        listings = parse(
            fetch(CITY, city_paths=RENTAL_CITY_PATHS, max_price=4000),
            target_city=CITY,
            min_price=300,
            max_price=4000,
        )
        upsert_rental_listings(clean_rental_db, listings)

        rows = clean_rental_db.query(RentalListing).order_by(RentalListing.id).all()
        assert len(rows) == 2
        assert {r.title for r in rows} == {"Rent A", "Rent B"}

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_price_change_tracked(self, mock_time, mock_curl, clean_rental_db):
        session = MagicMock()
        mock_curl.Session.return_value = session

        api_v1 = MagicMock(status_code=200)
        api_v1.json.return_value = _page([make_item(id=9101, href="[lang]/ad/r-ID9101", totalPrice={"value": 1000})])
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_v1]

        kwargs = dict(city_paths=RENTAL_CITY_PATHS, max_price=4000)
        parse_kwargs = dict(target_city=CITY, min_price=300, max_price=4000)

        upsert_rental_listings(clean_rental_db, parse(fetch(CITY, **kwargs), **parse_kwargs))

        api_v2 = MagicMock(status_code=200)
        api_v2.json.return_value = _page([make_item(id=9101, href="[lang]/ad/r-ID9101", totalPrice={"value": 950})])
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_v2]

        upsert_rental_listings(clean_rental_db, parse(fetch(CITY, **kwargs), **parse_kwargs))
        clean_rental_db.expire_all()

        assert clean_rental_db.query(RentalListing).filter_by(id="9101").first().price == 950
        history = clean_rental_db.query(RentalListingPriceHistory).filter_by(listing_id="9101").all()
        assert len(history) == 1
        assert history[0].price == 950

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_raw_json_stored(self, mock_time, mock_curl, clean_rental_db):
        session = MagicMock()
        mock_curl.Session.return_value = session
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _page([make_item(id=9201, href="[lang]/ad/rr-ID9201", totalPrice={"value": 1500})])
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_resp]

        listings = parse(
            fetch(CITY, city_paths=RENTAL_CITY_PATHS, max_price=4000),
            target_city=CITY,
            min_price=300,
            max_price=4000,
        )
        upsert_rental_listings(clean_rental_db, listings)

        raw = clean_rental_db.query(RentalRawData).filter_by(listing_id="9201").first()
        assert raw is not None
        assert raw.raw_json["id"] == 9201

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_deactivate_missing_after_scrape(self, mock_time, mock_curl, clean_rental_db):
        upsert_rental_listings(
            clean_rental_db,
            [
                {
                    "id": "r-active",
                    "source": "imovirtual",
                    "url": "https://x.com/a",
                    "price": 1000,
                    "active": True,
                    "inactive_since": None,
                    "last_seen": None,
                    "updated_at": None,
                },
                {
                    "id": "r-gone",
                    "source": "imovirtual",
                    "url": "https://x.com/b",
                    "price": 1000,
                    "active": True,
                    "inactive_since": None,
                    "last_seen": None,
                    "updated_at": None,
                },
            ],
        )
        deactivate_missing_rentals(clean_rental_db, "imovirtual", ["r-active"])

        assert clean_rental_db.query(RentalListing).filter_by(id="r-active").first().active is True
        gone = clean_rental_db.query(RentalListing).filter_by(id="r-gone").first()
        assert gone.active is False
        assert gone.inactive_since is not None

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_price_filter_excludes_out_of_range(self, mock_time, mock_curl, clean_rental_db):
        session = MagicMock()
        mock_curl.Session.return_value = session
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _page(
            [
                make_item(id=9301, href="[lang]/ad/ok-ID9301", totalPrice={"value": 1500}),
                make_item(id=9302, href="[lang]/ad/cheap-ID9302", totalPrice={"value": 100}),
                make_item(id=9303, href="[lang]/ad/exp-ID9303", totalPrice={"value": 9999}),
            ]
        )
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_resp]

        listings = parse(
            fetch(CITY, city_paths=RENTAL_CITY_PATHS, max_price=4000),
            target_city=CITY,
            min_price=300,
            max_price=4000,
        )
        upsert_rental_listings(clean_rental_db, listings)

        assert clean_rental_db.query(RentalListing).filter_by(id="9301").count() == 1
        assert clean_rental_db.query(RentalListing).filter_by(id="9302").count() == 0
        assert clean_rental_db.query(RentalListing).filter_by(id="9303").count() == 0

    @patch("scraper.imovirtual.fetcher.curl_requests")
    @patch("scraper.imovirtual.fetcher.time")
    def test_lifetime_rent_enrichment(self, mock_time, mock_curl, clean_rental_db):
        session = MagicMock()
        mock_curl.Session.return_value = session
        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = _page(
            [
                make_item(
                    id=9401,
                    href="[lang]/ad/vit-ID9401",
                    title="Apartamento arrendado",
                    shortDescription="Com inquilino",
                    totalPrice={"value": 800},
                )
            ]
        )
        session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), api_resp]

        listings = parse(
            fetch(CITY, city_paths=RENTAL_CITY_PATHS, max_price=4000),
            target_city=CITY,
            min_price=300,
            max_price=4000,
        )
        assert listings[0]["is_rented"] is True

        detail_session = MagicMock()
        mock_curl.Session.return_value = detail_session
        detail_resp = MagicMock(status_code=200)
        detail_resp.json.return_value = {"pageProps": {"ad": {"description": "Renda vitalicia garantida"}}}
        detail_session.get.side_effect = [MagicMock(status_code=200, text=BUILD_ID_HTML), detail_resp]

        upsert_rental_listings(clean_rental_db, fetch_details(listings, CITY, city_paths=RENTAL_CITY_PATHS))

        row = clean_rental_db.query(RentalListing).filter_by(id="9401").first()
        assert row.is_rented is True
        assert row.lifetime_rent is True
