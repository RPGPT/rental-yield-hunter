from datetime import datetime, timezone

from sqlalchemy import text

from db.models import Listing, ListingPriceHistory, RawData, RentalListing, RentalListingPriceHistory, RentalRawData
from db.repository import (
    _get_existing,
    _sanitize_url,
    deactivate_missing,
    deactivate_missing_rentals,
    upsert_listings,
    upsert_rental_listings,
)

_NOW = datetime.now(timezone.utc)

_BASE = {
    "id": "test-repo-1",
    "source": "imovirtual",
    "url": "https://example.com/test-repo-1",
    "title": "Test Listing",
    "description": "A test",
    "price": 200000,
    "area": 80,
    "price_per_m2": 2500.0,
    "location": "Paranhos, Porto",
    "neighborhood": "Paranhos",
    "city": "Porto",
    "property_type": "apartment",
    "typology": "T2",
    "floor": "3",
    "has_garage": True,
    "is_rented": False,
    "lifetime_rent": False,
    "active": True,
    "inactive_since": None,
    "last_seen": _NOW,
    "updated_at": _NOW,
}


class TestUpsertInsert:
    def test_inserts_new_listing(self, clean_db):
        upsert_listings(clean_db, [{**_BASE}])

        row = clean_db.query(Listing).filter(Listing.id == "test-repo-1").first()
        assert row is not None
        assert row.price == 200000
        assert row.title == "Test Listing"
        assert row.property_type == "apartment"
        assert row.typology == "T2"
        assert row.has_garage is True

    def test_inserts_multiple(self, clean_db):
        upsert_listings(
            clean_db,
            [
                {**_BASE, "id": "test-a", "url": "https://example.com/a"},
                {**_BASE, "id": "test-b", "url": "https://example.com/b"},
            ],
        )

        assert clean_db.query(Listing).count() == 2


class TestUpsertUpdate:
    def test_updates_existing_fields(self, clean_db):
        upsert_listings(clean_db, [{**_BASE}])
        upsert_listings(clean_db, [{**_BASE, "title": "Updated Title"}])

        assert clean_db.query(Listing).filter(Listing.id == "test-repo-1").first().title == "Updated Title"

    def test_preserves_first_seen(self, clean_db):
        upsert_listings(clean_db, [{**_BASE}])
        first_seen = clean_db.query(Listing).filter(Listing.id == "test-repo-1").first().first_seen

        upsert_listings(clean_db, [{**_BASE, "title": "Changed"}])
        clean_db.expire_all()

        assert clean_db.query(Listing).filter(Listing.id == "test-repo-1").first().first_seen == first_seen


class TestPriceHistory:
    def test_records_price_change(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "price": 200000}])
        upsert_listings(clean_db, [{**_BASE, "price": 190000}])

        history = clean_db.query(ListingPriceHistory).filter(ListingPriceHistory.listing_id == "test-repo-1").all()
        assert len(history) == 1
        assert history[0].price == 190000

    def test_no_record_when_price_unchanged(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "price": 200000}])
        upsert_listings(clean_db, [{**_BASE, "price": 200000}])

        history = clean_db.query(ListingPriceHistory).filter(ListingPriceHistory.listing_id == "test-repo-1").all()
        assert len(history) == 0

    def test_multiple_price_changes(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "price": 200000}])
        upsert_listings(clean_db, [{**_BASE, "price": 190000}])
        upsert_listings(clean_db, [{**_BASE, "price": 185000}])

        history = (
            clean_db.query(ListingPriceHistory)
            .filter(ListingPriceHistory.listing_id == "test-repo-1")
            .order_by(ListingPriceHistory.id)
            .all()
        )
        assert len(history) == 2
        assert history[0].price == 190000
        assert history[1].price == 185000


class TestLifetimeRent:
    def test_stores_lifetime_rent(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "is_rented": True, "lifetime_rent": True}])

        assert clean_db.query(Listing).filter(Listing.id == "test-repo-1").first().lifetime_rent is True

    def test_updates_lifetime_rent(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "is_rented": True, "lifetime_rent": False}])
        upsert_listings(clean_db, [{**_BASE, "is_rented": True, "lifetime_rent": True}])

        clean_db.expire_all()
        assert clean_db.query(Listing).filter(Listing.id == "test-repo-1").first().lifetime_rent is True


class TestRawData:
    def test_stores_raw_json(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "_raw_json": {"id": 99, "title": "Test"}}])

        row = clean_db.query(RawData).filter(RawData.listing_id == "test-repo-1").first()
        assert row is not None
        assert row.raw_json["id"] == 99

    def test_updates_raw_json_on_rescrape(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "_raw_json": {"version": 1}}])
        upsert_listings(clean_db, [{**_BASE, "_raw_json": {"version": 2}}])

        assert clean_db.query(RawData).filter(RawData.listing_id == "test-repo-1").first().raw_json["version"] == 2

    def test_no_raw_data_when_not_provided(self, clean_db):
        upsert_listings(clean_db, [{**_BASE}])

        assert clean_db.query(RawData).filter(RawData.listing_id == "test-repo-1").first() is None


class TestEmptyInput:
    def test_empty_list(self, clean_db):
        upsert_listings(clean_db, [])
        assert clean_db.query(Listing).count() == 0


class TestDeactivateMissing:
    def test_deactivates_missing_listing(self, clean_db):
        upsert_listings(
            clean_db,
            [
                {**_BASE, "id": "stay", "url": "https://example.com/stay"},
                {**_BASE, "id": "gone", "url": "https://example.com/gone"},
            ],
        )
        deactivate_missing(clean_db, "imovirtual", ["stay"])

        stay = clean_db.query(Listing).filter(Listing.id == "stay").first()
        assert stay.active is True
        assert stay.inactive_since is None

        gone = clean_db.query(Listing).filter(Listing.id == "gone").first()
        assert gone.active is False
        assert gone.inactive_since is not None

    def test_reactivates_on_rescrape(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "id": "flip", "url": "https://example.com/flip"}])
        deactivate_missing(clean_db, "imovirtual", [])
        upsert_listings(clean_db, [{**_BASE, "id": "flip", "url": "https://example.com/flip"}])
        clean_db.expire_all()

        row = clean_db.query(Listing).filter(Listing.id == "flip").first()
        assert row.active is True
        assert row.inactive_since is None

    def test_does_not_deactivate_other_sources(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "id": "other", "url": "https://example.com/other", "source": "idealista"}])
        deactivate_missing(clean_db, "imovirtual", [])

        assert clean_db.query(Listing).filter(Listing.id == "other").first().active is True

    def test_no_listings_no_crash(self, clean_db):
        deactivate_missing(clean_db, "imovirtual", [])

    def test_all_still_active(self, clean_db):
        upsert_listings(
            clean_db,
            [
                {**_BASE, "id": "a1", "url": "https://example.com/a1"},
                {**_BASE, "id": "a2", "url": "https://example.com/a2"},
            ],
        )
        deactivate_missing(clean_db, "imovirtual", ["a1", "a2"])

        for lid in ["a1", "a2"]:
            assert clean_db.query(Listing).filter(Listing.id == lid).first().active is True


class TestSanitizeUrl:
    def test_strips_hpr_from_full_url(self):
        assert (
            _sanitize_url("https://www.imovirtual.com/hpr/pt/anuncio/apartamento-t1-ID123")
            == "https://www.imovirtual.com/pt/anuncio/apartamento-t1-ID123"
        )

    def test_clean_url_unchanged(self):
        url = "https://www.imovirtual.com/pt/anuncio/apartamento-t1-ID123"
        assert _sanitize_url(url) == url

    def test_none_returns_none(self):
        assert _sanitize_url(None) is None

    def test_empty_returns_empty(self):
        assert _sanitize_url("") == ""

    def test_upsert_sanitizes_hpr_url(self, clean_db):
        upsert_listings(
            clean_db,
            [{**_BASE, "id": "hpr-test", "url": "https://www.imovirtual.com/hpr/pt/anuncio/apartamento-ID999"}],
        )

        row = clean_db.query(Listing).filter(Listing.id == "hpr-test").first()
        assert "/hpr/" not in row.url
        assert row.url == "https://www.imovirtual.com/pt/anuncio/apartamento-ID999"

    def test_upsert_corrects_existing_hpr_url(self, clean_db):
        bad_url = "https://www.imovirtual.com/hpr/pt/anuncio/apartamento-ID888"
        upsert_listings(clean_db, [{**_BASE, "id": "hpr-fix", "url": bad_url}])
        upsert_listings(clean_db, [{**_BASE, "id": "hpr-fix", "url": bad_url}])

        clean_db.expire_all()
        assert (
            clean_db.query(Listing).filter(Listing.id == "hpr-fix").first().url
            == "https://www.imovirtual.com/pt/anuncio/apartamento-ID888"
        )


class TestIsDeleted:
    def test_deleted_default_is_false(self, clean_db):
        upsert_listings(clean_db, [{**_BASE}])
        assert clean_db.query(Listing).filter_by(id="test-repo-1").first().is_deleted is False

    def test_deleted_listing_price_not_updated(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "price": 200000}])
        clean_db.execute(text("UPDATE listings SET is_deleted = true WHERE id = 'test-repo-1'"))
        clean_db.commit()
        upsert_listings(clean_db, [{**_BASE, "price": 150000}])
        clean_db.expire_all()
        assert clean_db.query(Listing).filter_by(id="test-repo-1").first().price == 200000

    def test_deleted_listing_all_fields_frozen(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "title": "Original", "city": "Porto"}])
        clean_db.execute(text("UPDATE listings SET is_deleted = true WHERE id = 'test-repo-1'"))
        clean_db.commit()
        upsert_listings(clean_db, [{**_BASE, "title": "Changed", "city": "Lisbon", "price": 99000}])
        clean_db.expire_all()
        row = clean_db.query(Listing).filter_by(id="test-repo-1").first()
        assert row.title == "Original"
        assert row.city == "Porto"
        assert row.price == 200000

    def test_deleted_listing_skips_price_history(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "price": 200000}])
        clean_db.execute(text("UPDATE listings SET is_deleted = true WHERE id = 'test-repo-1'"))
        clean_db.commit()
        upsert_listings(clean_db, [{**_BASE, "price": 150000}])
        assert clean_db.query(ListingPriceHistory).filter_by(listing_id="test-repo-1").count() == 0

    def test_deleted_listing_raw_data_not_updated(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "_raw_json": {"v": 1}}])
        clean_db.execute(text("UPDATE listings SET is_deleted = true WHERE id = 'test-repo-1'"))
        clean_db.commit()
        upsert_listings(clean_db, [{**_BASE, "_raw_json": {"v": 2}}])
        clean_db.expire_all()
        assert clean_db.query(RawData).filter_by(listing_id="test-repo-1").first().raw_json["v"] == 1

    def test_scraper_cannot_set_is_deleted_true(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "is_deleted": True}])
        assert clean_db.query(Listing).filter_by(id="test-repo-1").first().is_deleted is False

    def test_scraper_cannot_reset_is_deleted_to_false(self, clean_db):
        upsert_listings(clean_db, [{**_BASE}])
        clean_db.execute(text("UPDATE listings SET is_deleted = true WHERE id = 'test-repo-1'"))
        clean_db.commit()
        upsert_listings(clean_db, [{**_BASE, "is_deleted": False}])
        clean_db.expire_all()
        assert clean_db.query(Listing).filter_by(id="test-repo-1").first().is_deleted is True

    def test_non_deleted_listing_still_updates(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "price": 200000}])
        upsert_listings(clean_db, [{**_BASE, "price": 180000}])
        clean_db.expire_all()
        assert clean_db.query(Listing).filter_by(id="test-repo-1").first().price == 180000

    def test_only_deleted_listing_is_skipped_others_proceed(self, clean_db):
        upsert_listings(
            clean_db,
            [
                {**_BASE, "id": "keep", "url": "https://example.com/keep", "price": 200000},
                {**_BASE, "id": "del", "url": "https://example.com/del", "price": 200000},
            ],
        )
        clean_db.execute(text("UPDATE listings SET is_deleted = true WHERE id = 'del'"))
        clean_db.commit()
        upsert_listings(
            clean_db,
            [
                {**_BASE, "id": "keep", "url": "https://example.com/keep", "price": 111000},
                {**_BASE, "id": "del", "url": "https://example.com/del", "price": 111000},
            ],
        )
        clean_db.expire_all()
        assert clean_db.query(Listing).filter_by(id="keep").first().price == 111000
        assert clean_db.query(Listing).filter_by(id="del").first().price == 200000

    def test_deactivate_missing_skips_deleted_listings(self, clean_db):
        upsert_listings(clean_db, [{**_BASE, "id": "del", "url": "https://example.com/del"}])
        clean_db.execute(text("UPDATE listings SET is_deleted = true WHERE id = 'del'"))
        clean_db.commit()
        deactivate_missing(clean_db, "imovirtual", [])
        clean_db.expire_all()
        row = clean_db.query(Listing).filter_by(id="del").first()
        assert row.active is True
        assert row.inactive_since is None


_RENTAL_BASE = {
    **{k: v for k, v in _BASE.items() if k not in ("is_rented", "lifetime_rent")},
    "id": "rental-repo-1",
    "url": "https://example.com/rental-repo-1",
    "price": 1200,
    "area": 80,
    "rent_price_per_m2": 15.0,
}


class TestRentalUpsertInsert:
    def test_inserts_new_rental_listing(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE}])
        row = clean_rental_db.query(RentalListing).filter_by(id="rental-repo-1").first()
        assert row is not None
        assert row.price == 1200
        assert row.typology == "T2"
        assert row.rent_price_per_m2 == 15.0

    def test_is_rented_and_lifetime_rent_not_stored(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "is_rented": True, "lifetime_rent": True}])
        row = clean_rental_db.query(RentalListing).filter_by(id="rental-repo-1").first()
        assert not hasattr(row, "is_rented") or row.__class__.__table__.c.keys().count("is_rented") == 0

    def test_inserts_multiple(self, clean_rental_db):
        upsert_rental_listings(
            clean_rental_db,
            [
                {**_RENTAL_BASE, "id": "r-a", "url": "https://example.com/r-a"},
                {**_RENTAL_BASE, "id": "r-b", "url": "https://example.com/r-b"},
            ],
        )
        assert clean_rental_db.query(RentalListing).count() == 2

    def test_empty_list(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [])
        assert clean_rental_db.query(RentalListing).count() == 0


class TestRentalUpsertUpdate:
    def test_updates_existing_fields(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE}])
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "title": "Updated"}])
        assert clean_rental_db.query(RentalListing).filter_by(id="rental-repo-1").first().title == "Updated"

    def test_preserves_first_seen(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE}])
        first_seen = clean_rental_db.query(RentalListing).filter_by(id="rental-repo-1").first().first_seen
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "title": "Changed"}])
        clean_rental_db.expire_all()
        assert clean_rental_db.query(RentalListing).filter_by(id="rental-repo-1").first().first_seen == first_seen


class TestRentalPriceHistory:
    def test_records_price_change(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "price": 1200}])
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "price": 1100}])
        history = clean_rental_db.query(RentalListingPriceHistory).filter_by(listing_id="rental-repo-1").all()
        assert len(history) == 1
        assert history[0].price == 1100

    def test_no_record_when_price_unchanged(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "price": 1200}])
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "price": 1200}])
        assert clean_rental_db.query(RentalListingPriceHistory).filter_by(listing_id="rental-repo-1").count() == 0


class TestRentalRawData:
    def test_stores_raw_json(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "_raw_json": {"id": 99}}])
        row = clean_rental_db.query(RentalRawData).filter_by(listing_id="rental-repo-1").first()
        assert row is not None
        assert row.raw_json["id"] == 99

    def test_updates_raw_json_on_rescrape(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "_raw_json": {"v": 1}}])
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "_raw_json": {"v": 2}}])
        assert clean_rental_db.query(RentalRawData).filter_by(listing_id="rental-repo-1").first().raw_json["v"] == 2


class TestRentalIsDeleted:
    def test_deleted_listing_price_not_updated(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "price": 1200}])
        clean_rental_db.execute(text("UPDATE rental_listings SET is_deleted = true WHERE id = 'rental-repo-1'"))
        clean_rental_db.commit()
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "price": 800}])
        clean_rental_db.expire_all()
        assert clean_rental_db.query(RentalListing).filter_by(id="rental-repo-1").first().price == 1200

    def test_deleted_listing_skips_price_history(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "price": 1200}])
        clean_rental_db.execute(text("UPDATE rental_listings SET is_deleted = true WHERE id = 'rental-repo-1'"))
        clean_rental_db.commit()
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "price": 800}])
        assert clean_rental_db.query(RentalListingPriceHistory).filter_by(listing_id="rental-repo-1").count() == 0


class TestDeactivateMissingRentals:
    def test_deactivates_missing_rental(self, clean_rental_db):
        upsert_rental_listings(
            clean_rental_db,
            [
                {**_RENTAL_BASE, "id": "r-stay", "url": "https://example.com/r-stay"},
                {**_RENTAL_BASE, "id": "r-gone", "url": "https://example.com/r-gone"},
            ],
        )
        deactivate_missing_rentals(clean_rental_db, "imovirtual", ["r-stay"])

        assert clean_rental_db.query(RentalListing).filter_by(id="r-stay").first().active is True
        gone = clean_rental_db.query(RentalListing).filter_by(id="r-gone").first()
        assert gone.active is False
        assert gone.inactive_since is not None

    def test_does_not_touch_buy_listings(self, clean_db, clean_rental_db):
        upsert_listings(clean_db, [{**_BASE, "id": "buy-only", "url": "https://example.com/buy-only"}])
        deactivate_missing_rentals(clean_rental_db, "imovirtual", [])
        assert clean_db.query(Listing).filter_by(id="buy-only").first().active is True

    def test_skips_deleted_rentals(self, clean_rental_db):
        upsert_rental_listings(clean_rental_db, [{**_RENTAL_BASE, "id": "r-del", "url": "https://example.com/r-del"}])
        clean_rental_db.execute(text("UPDATE rental_listings SET is_deleted = true WHERE id = 'r-del'"))
        clean_rental_db.commit()
        deactivate_missing_rentals(clean_rental_db, "imovirtual", [])
        clean_rental_db.expire_all()
        row = clean_rental_db.query(RentalListing).filter_by(id="r-del").first()
        assert row.active is True
        assert row.inactive_since is None

    def test_scoped_to_city(self, clean_rental_db):
        upsert_rental_listings(
            clean_rental_db,
            [
                {**_RENTAL_BASE, "id": "r-porto", "url": "https://example.com/r-porto", "city": "Porto"},
                {**_RENTAL_BASE, "id": "r-maia", "url": "https://example.com/r-maia", "city": "Maia"},
            ],
        )
        deactivate_missing_rentals(clean_rental_db, "imovirtual", [], city="Porto")
        clean_rental_db.expire_all()
        assert clean_rental_db.query(RentalListing).filter_by(id="r-porto").first().active is False
        assert clean_rental_db.query(RentalListing).filter_by(id="r-maia").first().active is True


class TestGetExisting:
    def test_empty_ids_returns_empty_dict(self, db):
        # Exercises the early-return branch in _get_existing when ids=[]
        result = _get_existing(db, [], "listings")
        assert result == {}


class TestUpsertWithoutUrl:
    def test_listing_without_url_key_skips_sanitize(self):
        # A listing without a "url" key exercises the `if "url" in listing` False branch.
        # We use a mock session so the DB NOT NULL constraint is irrelevant.
        from unittest.mock import MagicMock, patch

        from db import repository

        sanitized = []
        original = repository._sanitize_url

        def spy(url):
            sanitized.append(url)
            return original(url)

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        no_url = {k: v for k, v in _BASE.items() if k != "url"}
        no_url["id"] = "no-url-id"

        with patch.object(repository, "_sanitize_url", side_effect=spy):
            repository._upsert(
                mock_db,
                [
                    {**_BASE, "id": "has-url"},  # url present → sanitized
                    no_url,  # url absent → branch False, sanitize not called
                ],
                repository.Listing,
                repository.ListingPriceHistory,
                repository.RawData,
            )

        # sanitize was called exactly once (only for the listing that has "url")
        assert len(sanitized) == 1
