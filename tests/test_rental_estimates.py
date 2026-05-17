import pytest
from sqlalchemy import text

from db.models import RentalEstimate
from db.repository import compute_and_upsert_rental_estimates, compute_rental_estimate, refresh_rental_estimates

_LISTING = {
    "id": "est-buy-1",
    "source": "imovirtual",
    "url": "https://example.com/est-buy-1",
    "title": "Buy Listing",
    "price": 250000,
    "area": 80,
    "price_per_m2": 3125.0,
    "neighborhood": "Parque das Nações",
    "city": "Lisboa",
    "typology": "T2",
    "active": True,
}

_RENTAL_BASE = {
    "source": "imovirtual",
    "url": "https://example.com/rental",
    "title": "Rental",
    "price": 1200,
    "area": 80,
    "neighborhood": "Parque das Nações",
    "city": "Lisboa",
    "typology": "T2",
    "rent_price_per_m2": 15.0,
    "active": True,
}


def _insert_listing(db, **overrides):
    data = {**_LISTING, **overrides}
    db.execute(
        text("""
            INSERT INTO listings
                (id, source, url, title, price, area, price_per_m2, neighborhood, city, typology, active)
            VALUES
                (:id, :source, :url, :title, :price, :area, :price_per_m2, :neighborhood, :city, :typology, :active)
            ON CONFLICT (id) DO NOTHING
        """),
        data,
    )
    db.commit()


def _insert_rentals(db, count: int, id_prefix: str = "est-rental", **overrides):
    for i in range(count):
        key = overrides.get("neighborhood", overrides.get("city", "n"))
        data = {**_RENTAL_BASE, **overrides, "id": f"{id_prefix}-{i}-{key}"}
        data.pop("id_prefix", None)
        db.execute(
            text("""
                INSERT INTO rental_listings
                    (id, source, url, title, price, area,
                     neighborhood, city, typology, rent_price_per_m2, active)
                VALUES
                    (:id, :source, :url, :title, :price, :area,
                     :neighborhood, :city, :typology, :rent_price_per_m2, :active)
                ON CONFLICT (id) DO NOTHING
            """),
            data,
        )
    db.commit()


@pytest.fixture
def estimate_db(db):
    yield db
    db.execute(text("DELETE FROM rental_estimates"))
    db.execute(text("DELETE FROM rental_listings"))
    db.execute(text("DELETE FROM listings"))
    db.commit()


class TestComputeRentalEstimate:
    def test_returns_none_for_missing_listing(self, estimate_db):
        result = compute_rental_estimate(estimate_db, "nonexistent-id")
        assert result is None

    def test_returns_none_when_area_missing(self, estimate_db):
        _insert_listing(estimate_db, id="est-no-area", area=None)
        result = compute_rental_estimate(estimate_db, "est-no-area")
        assert result is None

    def test_returns_none_when_typology_missing(self, estimate_db):
        _insert_listing(estimate_db, id="est-no-typo", typology=None)
        result = compute_rental_estimate(estimate_db, "est-no-typo")
        assert result is None

    def test_tier1_neighborhood_match(self, estimate_db):
        _insert_listing(estimate_db)
        _insert_rentals(estimate_db, 3, rent_price_per_m2=15.0)

        result = compute_rental_estimate(estimate_db, "est-buy-1")

        assert result is not None
        assert result["confidence"] == "high"
        assert result["match_level"] == "neighborhood"
        assert result["sample_count"] == 3
        assert result["avg_rent_per_m2"] == pytest.approx(15.0, abs=0.01)
        assert result["estimated_rent"] == round(15.0 * 80)

    def test_tier2_city_match_when_neighborhood_insufficient(self, estimate_db):
        _insert_listing(estimate_db)
        # Only 2 rentals in the neighbourhood — below MIN_SAMPLES
        _insert_rentals(estimate_db, 2, neighborhood="Parque das Nações", rent_price_per_m2=15.0)
        # 3 rentals in the same city but different neighbourhood
        _insert_rentals(estimate_db, 3, neighborhood="Belém", rent_price_per_m2=12.0)

        result = compute_rental_estimate(estimate_db, "est-buy-1")

        assert result is not None
        assert result["confidence"] == "medium"
        assert result["match_level"] == "city"

    def test_tier3_neighborhood_broad_match(self, estimate_db):
        _insert_listing(estimate_db)
        # 3 rentals in neighbourhood but with area outside ±15 % of 80 m²
        _insert_rentals(estimate_db, 3, area=200, rent_price_per_m2=10.0)

        result = compute_rental_estimate(estimate_db, "est-buy-1")

        assert result is not None
        assert result["confidence"] == "medium"
        assert result["match_level"] == "neighborhood_broad"

    def test_returns_none_confidence_when_no_tier_matches(self, estimate_db):
        _insert_listing(estimate_db)
        # Only 1 rental — below MIN_SAMPLES everywhere
        _insert_rentals(estimate_db, 1)

        result = compute_rental_estimate(estimate_db, "est-buy-1")

        assert result is not None
        assert result["confidence"] == "none"
        assert result["match_level"] == "none"
        assert result["estimated_rent"] is None
        assert result["sample_count"] == 0

    def test_ignores_inactive_rentals(self, estimate_db):
        _insert_listing(estimate_db)
        _insert_rentals(estimate_db, 3, active=False)

        result = compute_rental_estimate(estimate_db, "est-buy-1")

        assert result["confidence"] == "none"

    def test_ignores_rentals_without_rent_price_per_m2(self, estimate_db):
        _insert_listing(estimate_db)
        _insert_rentals(estimate_db, 3, rent_price_per_m2=None)

        result = compute_rental_estimate(estimate_db, "est-buy-1")

        assert result["confidence"] == "none"


class TestComputeAndUpsertRentalEstimates:
    def test_inserts_estimates(self, estimate_db):
        _insert_listing(estimate_db)
        _insert_rentals(estimate_db, 3)

        compute_and_upsert_rental_estimates(estimate_db, ["est-buy-1"])

        row = estimate_db.query(RentalEstimate).filter_by(listing_id="est-buy-1").first()
        assert row is not None
        assert row.confidence == "high"
        assert row.match_level == "neighborhood"

    def test_upserts_on_conflict(self, estimate_db):
        _insert_listing(estimate_db)
        _insert_rentals(estimate_db, 3, rent_price_per_m2=15.0)
        compute_and_upsert_rental_estimates(estimate_db, ["est-buy-1"])

        # Update rentals and recompute — estimate should be updated
        estimate_db.execute(text("UPDATE rental_listings SET rent_price_per_m2 = 20.0"))
        estimate_db.commit()
        compute_and_upsert_rental_estimates(estimate_db, ["est-buy-1"])

        row = estimate_db.query(RentalEstimate).filter_by(listing_id="est-buy-1").first()
        assert float(row.avg_rent_per_m2) == pytest.approx(20.0, abs=0.01)

    def test_skips_missing_area_or_typology(self, estimate_db):
        _insert_listing(estimate_db, id="est-skip", area=None)

        compute_and_upsert_rental_estimates(estimate_db, ["est-skip"])

        assert estimate_db.query(RentalEstimate).filter_by(listing_id="est-skip").first() is None

    def test_noop_on_empty_list(self, estimate_db):
        compute_and_upsert_rental_estimates(estimate_db, [])
        assert estimate_db.query(RentalEstimate).count() == 0

    def test_returns_count(self, estimate_db):
        _insert_listing(estimate_db)
        _insert_rentals(estimate_db, 3)

        count = compute_and_upsert_rental_estimates(estimate_db, ["est-buy-1"])

        assert count == 1

    def test_returns_zero_for_empty_list(self, estimate_db):
        assert compute_and_upsert_rental_estimates(estimate_db, []) == 0


class TestRefreshRentalEstimates:
    def test_covers_all_active_listings(self, estimate_db):
        _insert_listing(estimate_db, id="ref-buy-1", city="Lisboa", neighborhood="Belém", typology="T1", area=50)
        _insert_listing(estimate_db, id="ref-buy-2", city="Porto", neighborhood="Paranhos", typology="T2", area=80)
        _insert_rentals(
            estimate_db,
            3,
            id_prefix="ref-r1",
            city="Lisboa",
            neighborhood="Belém",
            typology="T1",
            area=50,
            rent_price_per_m2=14.0,
        )
        _insert_rentals(
            estimate_db,
            3,
            id_prefix="ref-r2",
            city="Porto",
            neighborhood="Paranhos",
            typology="T2",
            area=80,
            rent_price_per_m2=12.0,
        )

        count = refresh_rental_estimates(estimate_db)

        assert count == 2
        assert estimate_db.query(RentalEstimate).count() == 2

    def test_skips_inactive_listings(self, estimate_db):
        _insert_listing(estimate_db, id="ref-active", active=True)
        _insert_listing(estimate_db, id="ref-inactive", active=False)
        _insert_rentals(estimate_db, 3)

        refresh_rental_estimates(estimate_db)

        assert estimate_db.query(RentalEstimate).filter_by(listing_id="ref-active").first() is not None
        assert estimate_db.query(RentalEstimate).filter_by(listing_id="ref-inactive").first() is None

    def test_skips_deleted_listings(self, estimate_db):
        _insert_listing(estimate_db, id="ref-live")
        estimate_db.execute(
            text(
                "INSERT INTO listings (id, source, url, active, is_deleted)"
                " VALUES ('ref-deleted', 'imovirtual', 'https://x.com', true, true)"
            )
        )
        estimate_db.commit()
        _insert_rentals(estimate_db, 3)

        refresh_rental_estimates(estimate_db)

        assert estimate_db.query(RentalEstimate).filter_by(listing_id="ref-deleted").first() is None

    def test_returns_zero_when_no_listings(self, estimate_db):
        count = refresh_rental_estimates(estimate_db)
        assert count == 0
