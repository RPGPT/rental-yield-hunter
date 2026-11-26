"""Tests for saved-search filter matching, alert deduplication, and webhook/Telegram dispatch."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from yieldhunter.analysis.alerts import format_alert_digest_markdown, matches_saved_search
from yieldhunter.db.models import AlertNotification, RentalEstimate, SavedSearch
from yieldhunter.db.repository import find_pending_saved_search_alerts, upsert_listings
from yieldhunter.db.session import configure_session, reset_session
from yieldhunter.pipeline.alerts import run_send_alerts


@pytest.fixture
def alert_db(db):
    yield db
    db.execute(text("DELETE FROM alert_notifications"))
    db.execute(text("DELETE FROM saved_searches"))
    db.execute(text("DELETE FROM rental_estimates"))
    db.execute(text("DELETE FROM listing_clusters"))
    db.execute(text("DELETE FROM raw_data"))
    db.execute(text("DELETE FROM listing_price_history"))
    db.execute(text("DELETE FROM listings"))
    db.commit()


class TestMatchesSavedSearch:
    def test_matches_camel_and_snake_case_filters(self):
        listing = {
            "city": "Porto",
            "neighborhood": "Paranhos",
            "source": "imovirtual",
            "typology": "T2",
            "price": 210_000,
            "area": 82,
            "rental_yield": 0.068,
            "is_rented": False,
            "lifetime_rent": False,
            "has_garage": True,
            "price_drop_pct": 0.08,
            "is_cheapest": True,
        }
        assert matches_saved_search(
            listing,
            {
                "cities": ["Porto", "Maia"],
                "typologies": ["T2", "T3"],
                "maxPrice": 250_000,
                "minYield": 6.5,  # percentage form normalized to 0.065
                "excludeLifetimeRent": True,
                "minPriceDropPct": 5.0,
            },
        )
        assert not matches_saved_search(listing, {"minYield": 7.5})
        assert not matches_saved_search(listing, {"cities": ["Matosinhos"]})

    def test_digest_formatting(self):
        md = format_alert_digest_markdown(
            "High Yield Porto",
            [
                {
                    "id": "1",
                    "url": "https://example.com/1",
                    "city": "Porto",
                    "neighborhood": "Bonfim",
                    "typology": "T2",
                    "area": 75,
                    "price": 185_000,
                    "previous_price": 199_000,
                    "trigger_type": "price_drop",
                    "rental_yield": 0.072,
                    "estimated_rent": 1110,
                    "cluster_size": 2,
                    "price_spread": 10_000,
                    "is_cheapest": True,
                }
            ],
        )
        assert "📉 Price Drop" in md
        assert "€185,000 (was €199,000)" in md
        assert "7.2% yield" in md
        assert "€10,000 cheaper than rival agency" in md


class TestSavedSearchAlertsEndToEnd:
    def test_new_listing_and_price_drop_triggers_and_deduplicates(self, alert_db, test_engine, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        configure_session(test_engine)
        try:
            checked_at = datetime.now(timezone.utc) - timedelta(hours=2)
            search = SavedSearch(
                user_id="user-123",
                name="Porto Yield >= 6%",
                filters={"city": "Porto", "minYield": 6.0, "webhook_url": "https://hooks.example.com/deals"},
                last_checked_at=checked_at,
            )
            alert_db.add(search)
            alert_db.commit()

            now = datetime.now(timezone.utc)
            upsert_listings(
                alert_db,
                [
                    {
                        "id": "alert-deal-1",
                        "source": "era",
                        "url": "https://www.era.pt/imovel/1",
                        "title": "T2 Paranhos",
                        "description": "",
                        "price": 190_000,
                        "area": 78,
                        "price_per_m2": 2435.9,
                        "location": "Paranhos, Porto",
                        "neighborhood": "Paranhos",
                        "city": "Porto",
                        "property_type": "apartment",
                        "typology": "T2",
                        "floor": "2",
                        "has_garage": True,
                        "is_rented": False,
                        "lifetime_rent": False,
                        "active": True,
                        "inactive_since": None,
                        "last_seen": now,
                        "updated_at": now,
                    }
                ],
            )
            alert_db.add(
                RentalEstimate(
                    listing_id="alert-deal-1",
                    estimated_rent=1050,
                    avg_rent_per_m2=13.46,
                    sample_count=8,
                    confidence="high",
                    match_level="neighborhood",
                    rental_yield=0.0663,
                )
            )
            alert_db.commit()

            bundles = find_pending_saved_search_alerts(alert_db)
            assert len(bundles) == 1
            assert len(bundles[0]["matches"]) == 1
            assert bundles[0]["matches"][0]["trigger_type"] == "new"

            # Dispatch via webhook and verify dedup prevents duplicate sends on immediate re-run
            with patch("yieldhunter.pipeline.alerts._post_json", return_value=True) as mock_post:
                stats_1 = run_send_alerts()
                stats_2 = run_send_alerts()

            assert stats_1["notifications_sent"] == 1
            assert stats_2["notifications_sent"] == 0
            assert mock_post.call_count == 1
            assert alert_db.query(AlertNotification).count() == 1

            # Now drop the price by €15k -> must trigger a new 'price_drop' alert!
            upsert_listings(
                alert_db,
                [
                    {
                        "id": "alert-deal-1",
                        "source": "era",
                        "url": "https://www.era.pt/imovel/1",
                        "title": "T2 Paranhos",
                        "description": "",
                        "price": 175_000,
                        "area": 78,
                        "price_per_m2": 2243.6,
                        "location": "Paranhos, Porto",
                        "neighborhood": "Paranhos",
                        "city": "Porto",
                        "property_type": "apartment",
                        "typology": "T2",
                        "floor": "2",
                        "has_garage": True,
                        "is_rented": False,
                        "lifetime_rent": False,
                        "active": True,
                        "inactive_since": None,
                        "last_seen": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                ],
            )
            with patch("yieldhunter.pipeline.alerts._post_json", return_value=True):
                stats_3 = run_send_alerts()

            assert stats_3["notifications_sent"] == 1
            drop_notif = (
                alert_db.query(AlertNotification).filter_by(listing_id="alert-deal-1", triggered_price=175_000).one()
            )
            assert drop_notif.trigger_type == "price_drop"
        finally:
            reset_session()
