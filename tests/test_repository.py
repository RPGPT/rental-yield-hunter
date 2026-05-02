import pytest
from datetime import datetime, timezone

from db.models import Listing, ListingPriceHistory, RawData
from db.repository import upsert_listings


def _listing(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": "test-repo-1",
        "source": "imovirtual",
        "url": "https://example.com/test-repo-1",
        "title": "Test Listing",
        "description": "A test",
        "price": 200000,
        "area": 80,
        "price_per_m2": 2500.0,
        "location": "Paranhos, Porto",
        "city": "Paranhos",
        "parish": None,
        "property_type": "apartment",
        "typology": "T2",
        "floor": "3",
        "has_elevator": None,
        "has_garage": True,
        "condition": None,
        "rent_detected": None,
        "is_rented": False,
        "last_seen": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


class TestUpsertInsert:
    def test_inserts_new_listing(self, clean_db):
        data = _listing()
        upsert_listings(clean_db, [data])

        row = clean_db.query(Listing).filter(Listing.id == "test-repo-1").first()
        assert row is not None
        assert row.price == 200000
        assert row.title == "Test Listing"
        assert row.property_type == "apartment"
        assert row.typology == "T2"
        assert row.has_garage is True

    def test_inserts_multiple(self, clean_db):
        a = _listing(id="test-a", url="https://example.com/a")
        b = _listing(id="test-b", url="https://example.com/b")
        upsert_listings(clean_db, [a, b])

        count = clean_db.query(Listing).count()
        assert count == 2


class TestUpsertUpdate:
    def test_updates_existing_fields(self, clean_db):
        upsert_listings(clean_db, [_listing()])
        upsert_listings(clean_db, [_listing(title="Updated Title", price=200000)])

        row = clean_db.query(Listing).filter(Listing.id == "test-repo-1").first()
        assert row.title == "Updated Title"

    def test_preserves_first_seen(self, clean_db):
        upsert_listings(clean_db, [_listing()])
        row1 = clean_db.query(Listing).filter(Listing.id == "test-repo-1").first()
        first_seen = row1.first_seen

        upsert_listings(clean_db, [_listing(title="Changed")])
        clean_db.expire_all()
        row2 = clean_db.query(Listing).filter(Listing.id == "test-repo-1").first()
        assert row2.first_seen == first_seen


class TestPriceHistory:
    def test_records_price_change(self, clean_db):
        upsert_listings(clean_db, [_listing(price=200000)])
        upsert_listings(clean_db, [_listing(price=190000)])

        history = clean_db.query(ListingPriceHistory).filter(
            ListingPriceHistory.listing_id == "test-repo-1"
        ).all()
        assert len(history) == 1
        assert history[0].price == 190000

    def test_no_record_when_price_unchanged(self, clean_db):
        upsert_listings(clean_db, [_listing(price=200000)])
        upsert_listings(clean_db, [_listing(price=200000)])

        history = clean_db.query(ListingPriceHistory).filter(
            ListingPriceHistory.listing_id == "test-repo-1"
        ).all()
        assert len(history) == 0

    def test_multiple_price_changes(self, clean_db):
        upsert_listings(clean_db, [_listing(price=200000)])
        upsert_listings(clean_db, [_listing(price=190000)])
        upsert_listings(clean_db, [_listing(price=185000)])

        history = clean_db.query(ListingPriceHistory).filter(
            ListingPriceHistory.listing_id == "test-repo-1"
        ).order_by(ListingPriceHistory.id).all()
        assert len(history) == 2
        assert history[0].price == 190000
        assert history[1].price == 185000


class TestRawData:
    def test_stores_raw_json(self, clean_db):
        raw = {"id": 99, "title": "Test"}
        upsert_listings(clean_db, [_listing(_raw_json=raw)])

        row = clean_db.query(RawData).filter(RawData.listing_id == "test-repo-1").first()
        assert row is not None
        assert row.raw_json["id"] == 99

    def test_updates_raw_json_on_rescrape(self, clean_db):
        upsert_listings(clean_db, [_listing(_raw_json={"version": 1})])
        upsert_listings(clean_db, [_listing(_raw_json={"version": 2})])

        row = clean_db.query(RawData).filter(RawData.listing_id == "test-repo-1").first()
        assert row.raw_json["version"] == 2

    def test_no_raw_data_when_not_provided(self, clean_db):
        upsert_listings(clean_db, [_listing()])

        row = clean_db.query(RawData).filter(RawData.listing_id == "test-repo-1").first()
        assert row is None


class TestEmptyInput:
    def test_empty_list(self, clean_db):
        upsert_listings(clean_db, [])
        assert clean_db.query(Listing).count() == 0

