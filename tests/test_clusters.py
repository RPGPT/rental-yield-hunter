"""Tests for cross-source / multi-agency deduplication and price-arbitrage clustering."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from yieldhunter.analysis.clustering import build_listing_clusters, normalize_floor
from yieldhunter.db.models import ListingCluster
from yieldhunter.db.repository import refresh_listing_clusters, upsert_listings

_NOW = datetime.now(timezone.utc)


@pytest.fixture
def cluster_db(db):
    yield db
    db.execute(text("DELETE FROM listing_clusters"))
    db.execute(text("DELETE FROM raw_data"))
    db.execute(text("DELETE FROM listing_price_history"))
    db.execute(text("DELETE FROM listings"))
    db.commit()


class TestNormalizeFloor:
    def test_handles_words_ordinals_and_ground_aliases(self):
        assert normalize_floor("GROUND") == "0"
        assert normalize_floor("R/C") == "0"
        assert normalize_floor("rés-do-chão") == "0"
        assert normalize_floor("FIRST") == "1"
        assert normalize_floor("3º andar") == "3"
        assert normalize_floor(None) is None


class TestBuildListingClusters:
    def test_merges_same_apartment_across_sources_and_computes_spread(self):
        listings = [
            {
                "id": "imo-1",
                "source": "imovirtual",
                "city": "Porto",
                "neighborhood": "Paranhos",
                "typology": "T2",
                "area": 85,
                "price": 249_000,
                "floor": "SECOND",
                "has_garage": True,
                "location": "Rua de Costa Cabral, Paranhos, Porto",
                "title": "Apartamento T2 Costa Cabral",
                "description": "",
            },
            {
                "id": "era-1",
                "source": "era",
                "city": "Porto",
                "neighborhood": "Paranhos",
                "typology": "T2",
                "area": 84,
                "price": 239_000,
                "floor": "2",
                "has_garage": True,
                "location": "Rua de Costa Cabral, Paranhos, Porto",
                "title": "Apartamento T2 Paranhos",
                "description": "",
            },
            {
                "id": "cs-1",
                "source": "casasapo",
                "city": "Porto",
                "neighborhood": "Paranhos",
                "typology": "T2",
                "area": 85,
                "price": 255_000,
                "floor": "2",
                "has_garage": True,
                "location": "Rua de Costa Cabral, Paranhos, Porto",
                "title": "Apartamento T2 Rua de Costa Cabral",
                "description": "",
            },
        ]

        rows = {r["listing_id"]: r for r in build_listing_clusters(listings)}
        assert len({r["cluster_id"] for r in rows.values()}) == 1

        era_row = rows["era-1"]
        assert era_row["cluster_size"] == 3
        assert era_row["cluster_min_price"] == 239_000
        assert era_row["cluster_max_price"] == 255_000
        assert era_row["price_spread"] == 16_000
        assert era_row["is_cheapest"] is True
        assert era_row["sources"] == ["casasapo", "era", "imovirtual"]
        assert rows["imo-1"]["is_cheapest"] is False
        assert rows["cs-1"]["is_cheapest"] is False

    def test_does_not_merge_conflicting_floors_or_streets(self):
        base = {
            "source": "imovirtual",
            "city": "Porto",
            "neighborhood": "Paranhos",
            "typology": "T2",
            "area": 85,
            "price": 240_000,
            "has_garage": True,
            "title": "Apartamento T2",
            "description": "",
        }
        a = {**base, "id": "a", "floor": "1", "location": "Rua A, Paranhos, Porto"}
        b_diff_floor = {**base, "id": "b", "floor": "3", "location": "Rua A, Paranhos, Porto"}
        c_diff_street = {**base, "id": "c", "floor": "1", "location": "Rua B, Paranhos, Porto"}

        rows = {r["listing_id"]: r for r in build_listing_clusters([a, b_diff_floor, c_diff_street])}
        assert len({r["cluster_id"] for r in rows.values()}) == 3
        assert all(r["cluster_size"] == 1 for r in rows.values())


class TestRefreshListingClustersDB:
    def test_persists_clusters_and_cleans_inactive(self, cluster_db):
        upsert_listings(
            cluster_db,
            [
                {
                    "id": "db-c1",
                    "source": "imovirtual",
                    "url": "https://example.com/1",
                    "title": "T2 Rua da Alegria",
                    "description": "",
                    "price": 220_000,
                    "area": 80,
                    "price_per_m2": 2750.0,
                    "location": "Rua da Alegria, Bonfim, Porto",
                    "neighborhood": "Bonfim",
                    "city": "Porto",
                    "property_type": "apartment",
                    "typology": "T2",
                    "floor": "1",
                    "has_garage": False,
                    "is_rented": False,
                    "lifetime_rent": False,
                    "active": True,
                    "inactive_since": None,
                    "last_seen": _NOW,
                    "updated_at": _NOW,
                },
                {
                    "id": "db-c2",
                    "source": "era",
                    "url": "https://example.com/2",
                    "title": "Apartamento T2 Rua da Alegria",
                    "description": "",
                    "price": 210_000,
                    "area": 80,
                    "price_per_m2": 2625.0,
                    "location": "Rua da Alegria, Bonfim, Porto",
                    "neighborhood": "Bonfim",
                    "city": "Porto",
                    "property_type": "apartment",
                    "typology": "T2",
                    "floor": "1",
                    "has_garage": False,
                    "is_rented": False,
                    "lifetime_rent": False,
                    "active": True,
                    "inactive_since": None,
                    "last_seen": _NOW,
                    "updated_at": _NOW,
                },
            ],
        )

        stats = refresh_listing_clusters(cluster_db, city="Porto")
        assert stats["listings"] == 2
        assert stats["multi_agency_clusters"] == 1
        assert stats["duplicate_listings"] == 2

        cheapest = cluster_db.query(ListingCluster).filter_by(listing_id="db-c2").one()
        assert cheapest.is_cheapest is True
        assert cheapest.price_spread == 10_000
