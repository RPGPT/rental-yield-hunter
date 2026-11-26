"""End-to-end characterization, lifecycle, and optimization flow tests backed by real recorded HTTP data.

Covers:
1. Golden baseline sanity checks (real Imovirtual + ERA listings, parish city, estimates, contracts).
2. Exact golden snapshot match across the full daily pipeline (buy -> rent -> contracts -> estimates)
   PLUS GitHub Actions summary rendering (`yieldhunter.pipeline.stats.render_job_summary`).
3. Multi-run lifecycle mutations on real data:
   - Price changes recorded in `listing_price_history` / `rental_listing_price_history` (changes only, never initial)
   - Deactivation scoped strictly by `(source, city)` and automatic reactivation when a listing reappears
   - `is_deleted` guard across upsert, price history, raw_data, deactivation, estimates, and contracts
4. Refactored flow improvements & optimizations:
   - Incomplete scrape safety: HTTP failures on token/buildId or mid-pagination preserve existing active listings
   - DB-first contract extraction: zero HTTP requests when `raw_data.fullDescription` was already captured
   - Lazy DB configuration: importing `main` / `yieldhunter` succeeds without `DATABASE_URL`
   - CLI entrypoint flags (`--source`, `--type`, `--city`, `--parallel`, `--stats-dir`)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
from alembic import command
from alembic.config import Config
from freezegun import freeze_time
from sqlalchemy import create_engine, text

from tests.flows.http_replay import FakeResponse, Replayer, load_recording
from tests.flows.snapshot import dump_db_snapshot
from yieldhunter.db.session import configure_session, reset_session
from yieldhunter.pipeline.stats import render_job_summary

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
GOLDEN_PATH = ROOT_DIR / "tests" / "golden" / "baseline.json"


@pytest.fixture(scope="module")
def recording() -> dict:
    return load_recording("recording")


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def flow_engine(pg):
    """Separate database inside the shared Postgres container, built via real Alembic migrations."""
    admin_engine = create_engine(pg.get_connection_url(), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS flow_test"))
        conn.execute(text("CREATE DATABASE flow_test"))
    admin_engine.dispose()

    base_url = pg.get_connection_url()
    flow_url = base_url.rsplit("/", 1)[0] + "/flow_test"

    alembic_cfg = Config(str(ROOT_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", flow_url)
    prev_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = flow_url
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if prev_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev_db_url

    engine = create_engine(flow_url)
    yield engine
    engine.dispose()


def _reset_flow_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                TRUNCATE TABLE
                    alert_notifications,
                    saved_searches,
                    listing_clusters,
                    rent_contract_details,
                    rental_estimates,
                    raw_data,
                    listing_price_history,
                    listings,
                    rental_raw_data,
                    rental_listing_price_history,
                    rental_listings
                RESTART IDENTITY CASCADE
                """
            )
        )


@pytest.fixture
def isolated_app_db(flow_engine, monkeypatch):
    """Point ``yieldhunter.db.session`` at the clean migrated flow DB."""
    _reset_flow_tables(flow_engine)
    flow_url = flow_engine.url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", flow_url)
    session_factory = configure_session(flow_engine)
    yield session_factory
    reset_session()


class TestGoldenDataSanity:
    def test_real_data_covers_both_sources_and_all_recorded_cities(self, golden):
        buy = golden["db"]["listings"]
        rent = golden["db"]["rental_listings"]
        assert len(buy) >= 50
        assert len(rent) >= 20

        buy_pairs = {(r["source"], r["city"]) for r in buy}
        for city in golden["meta"]["cities"]:
            assert ("imovirtual", city) in buy_pairs
            assert ("era", city) in buy_pairs

        rent_cities = {r["city"] for r in rent}
        assert set(golden["meta"]["cities"]).issubset(rent_cities)

    def test_invariants_hold_on_recorded_data(self, golden):
        for r in golden["db"]["listings"]:
            assert 50_000 <= r["price"] <= 405_000
            assert "/hpr/" not in r["url"]
            assert r["city"] in golden["meta"]["cities"]
            assert r["neighborhood"] is not None
            if r["source"] == "era":
                assert r["id"].startswith("era-")

        for r in golden["db"]["rental_listings"]:
            assert 300 <= r["price"] <= 4_000
            assert "/hpr/" not in r["url"]
            assert r["city"] in golden["meta"]["cities"]

        assert any(r["is_rented"] for r in golden["db"]["listings"])
        assert len(golden["db"]["rent_contract_details"]) >= 1
        levels = {e["match_level"] for e in golden["db"]["rental_estimates"]}
        assert len(levels - {"none"}) >= 2


class TestFullPipelineGoldenMatch:
    def test_full_pipeline_matches_golden_snapshot_and_renders_summary(
        self, isolated_app_db, recording, golden, tmp_path, monkeypatch
    ):
        import main as app_main

        monkeypatch.chdir(tmp_path)
        replayer = Replayer(recording)
        recorded_at = recording["meta"]["recorded_at"]

        run_stats = []
        with (
            freeze_time(recorded_at),
            replayer.patch(),
            mock.patch("time.sleep", return_value=None),
        ):
            for source in recording["meta"]["sources"]:
                for city in recording["meta"]["cities"]:
                    run_stats.append(app_main.scrape_city(source, city, "buy"))
            for source in recording["meta"]["sources"]:
                for city in recording["meta"]["cities"]:
                    run_stats.append(app_main.scrape_city(source, city, "rent"))

        # Contract extraction must now succeed with ZERO HTTP requests using stored descriptions
        empty_replayer = Replayer({"meta": recording["meta"], "exchanges": []})
        with (
            freeze_time(recorded_at),
            empty_replayer.patch(),
            mock.patch("time.sleep", return_value=None),
        ):
            contract_stats = app_main.run_extract_contracts(city=None)
            estimate_stats = app_main.run_refresh_estimates(city=None)
            cluster_stats = app_main.run_refresh_clusters(city=None)
            alert_stats = app_main.run_send_alerts()

        assert replayer.unrecorded == []
        assert empty_replayer.requests == []
        assert run_stats == golden["scrape_stats"]
        assert estimate_stats == golden["estimate_stats"]
        assert contract_stats == golden["contract_stats"]
        assert cluster_stats["listings"] == len(golden["db"]["listings"])
        assert alert_stats["searches_matched"] == 0

        with isolated_app_db() as db:
            actual_snapshot = dump_db_snapshot(db)
            # Verify lease-upside fields populated on extracted contracts
            upside_rows = (
                db.execute(text("SELECT current_yield, reversion_yield, rent_upside_pct FROM rent_contract_details"))
                .mappings()
                .all()
            )
            assert len(upside_rows) == 3
            assert all(r["current_yield"] is not None for r in upside_rows)
            assert any(r["reversion_yield"] is not None and r["rent_upside_pct"] is not None for r in upside_rows)

        assert actual_snapshot == golden["db"]

        # Verify stats JSON artifacts and summary table generation
        written_stats = sorted(p.name for p in tmp_path.glob("stats-*.json"))
        assert "stats-estimates-all.json" in written_stats
        assert "stats-contracts-all.json" in written_stats
        assert "stats-buy-imovirtual-Ermesinde.json" in written_stats
        assert "stats-rent-era-Maia.json" in written_stats

        summary_md = render_job_summary(tmp_path)
        assert "### 🛒 Buy" in summary_md
        assert "### 🔑 Rent" in summary_md
        assert "### 📋 Contract Details" in summary_md
        assert "### 📊 Rent Estimates" in summary_md
        assert "### 🔗 Multi-Agency Clusters" in summary_md
        assert "### 🔔 Deal Alerts" in summary_md
        assert "| Ermesinde |" in summary_md
        assert "| Maia |" in summary_md
        assert "| Penafiel |" in summary_md


class TestStatefulLifecycleFlows:
    def test_price_changes_deactivation_reactivation_and_is_deleted_guard(
        self, isolated_app_db, recording, tmp_path, monkeypatch
    ):
        import main as app_main

        monkeypatch.chdir(tmp_path)
        recorded_at = recording["meta"]["recorded_at"]

        # ── Run 1: scrape Penafiel + Ermesinde (Imovirtual buy & rent) + ERA Ermesinde buy ──
        r1 = Replayer(recording)
        with freeze_time(recorded_at), r1.patch(), mock.patch("time.sleep", return_value=None):
            app_main.scrape_city("imovirtual", "Penafiel", "buy")
            s1_erm = app_main.scrape_city("imovirtual", "Ermesinde", "buy")
            app_main.scrape_city("era", "Ermesinde", "buy")
            app_main.scrape_city("imovirtual", "Ermesinde", "rent")

        assert s1_erm["fetched"] >= 5

        with isolated_app_db() as db:
            erm_ids = [
                r[0]
                for r in db.execute(
                    text(
                        "SELECT id FROM listings "
                        "WHERE source = 'imovirtual' AND city = 'Ermesinde' AND id != '9000062349' ORDER BY id"
                    )
                ).fetchall()
            ]
            rent_ids = [
                r[0]
                for r in db.execute(
                    text(
                        "SELECT id FROM rental_listings "
                        "WHERE source = 'imovirtual' AND city = 'Ermesinde' AND id != '9000062349' ORDER BY id"
                    )
                ).fetchall()
            ]
            penafiel_count = db.execute(
                text(
                    "SELECT COUNT(*) FROM listings WHERE source = 'imovirtual' AND city = 'Penafiel' AND active = true"
                )
            ).scalar_one()
            era_erm_count = db.execute(
                text("SELECT COUNT(*) FROM listings WHERE source = 'era' AND city = 'Ermesinde' AND active = true")
            ).scalar_one()

            changed_id, dropped_id, deleted_id = erm_ids[0], erm_ids[1], erm_ids[2]
            changed_rent_id = rent_ids[0]

            orig_deleted = (
                db.execute(text("SELECT price, url, title FROM listings WHERE id = :id"), {"id": deleted_id})
                .mappings()
                .one()
            )
            orig_changed_price = db.execute(
                text("SELECT price FROM listings WHERE id = :id"), {"id": changed_id}
            ).scalar_one()
            orig_rent_price = db.execute(
                text("SELECT price FROM rental_listings WHERE id = :id"), {"id": changed_rent_id}
            ).scalar_one()

            # Simulate user deleting `deleted_id` from the frontend
            db.execute(text("UPDATE listings SET is_deleted = true WHERE id = :id"), {"id": deleted_id})
            db.commit()

        # ── Run 2: mutate search feed — raise price on changed_id & changed_rent_id,
        #           raise price on deleted_id (must be ignored!), and drop dropped_id ──
        def mutate_feed(url: str, _ex: dict, data):
            if not isinstance(data, dict):
                return data
            search_ads = ((data.get("pageProps") or {}).get("data") or {}).get("searchAds")
            if not search_ads:
                return data
            new_items = []
            for item in search_ads.get("items", []):
                item_id = str(item.get("id", ""))
                if item_id == dropped_id:
                    continue
                if item_id == changed_id:
                    item["totalPrice"]["value"] = orig_changed_price + 7_500
                elif item_id == deleted_id:
                    item["totalPrice"]["value"] = orig_deleted["price"] + 9_999
                    item["title"] = "SHOULD NEVER OVERWRITE DELETED"
                elif item_id == changed_rent_id:
                    item["totalPrice"]["value"] = orig_rent_price + 75
                new_items.append(item)
            search_ads["items"] = new_items
            return data

        r2 = Replayer(recording, transform=mutate_feed)
        with freeze_time(recorded_at), r2.patch(), mock.patch("time.sleep", return_value=None):
            s2_erm = app_main.scrape_city("imovirtual", "Ermesinde", "buy")
            s2_rent = app_main.scrape_city("imovirtual", "Ermesinde", "rent")
            app_main.run_refresh_estimates(city="Ermesinde")
            app_main.run_extract_contracts(city="Ermesinde")

        assert s2_erm["price_changes"] == 1
        assert s2_rent["price_changes"] == 1

        with isolated_app_db() as db:
            new_price = db.execute(text("SELECT price FROM listings WHERE id = :id"), {"id": changed_id}).scalar_one()
            assert new_price == orig_changed_price + 7_500
            sig = (
                db.execute(
                    text("SELECT initial_price, price_drop_amount, price_change_count FROM listings WHERE id = :id"),
                    {"id": changed_id},
                )
                .mappings()
                .one()
            )
            assert sig["initial_price"] == orig_changed_price
            assert sig["price_drop_amount"] == -7_500
            assert sig["price_change_count"] == 1
            hist = db.execute(
                text("SELECT previous_price, price FROM listing_price_history WHERE listing_id = :id"),
                {"id": changed_id},
            ).fetchall()
            assert [(h[0], h[1]) for h in hist] == [(orig_changed_price, orig_changed_price + 7_500)]

            rent_hist = (
                db.execute(
                    text("SELECT price FROM rental_listing_price_history WHERE listing_id = :id"),
                    {"id": changed_rent_id},
                )
                .scalars()
                .all()
            )
            assert rent_hist == [orig_rent_price + 75]

            dropped_row = (
                db.execute(text("SELECT active, inactive_since FROM listings WHERE id = :id"), {"id": dropped_id})
                .mappings()
                .one()
            )
            assert dropped_row["active"] is False
            assert dropped_row["inactive_since"] is not None

            assert (
                db.execute(
                    text(
                        "SELECT COUNT(*) FROM listings "
                        "WHERE source = 'imovirtual' AND city = 'Penafiel' AND active = true"
                    )
                ).scalar_one()
                == penafiel_count
            )
            assert (
                db.execute(
                    text("SELECT COUNT(*) FROM listings WHERE source = 'era' AND city = 'Ermesinde' AND active = true")
                ).scalar_one()
                == era_erm_count
            )

            del_row = (
                db.execute(
                    text("SELECT price, title, is_deleted, active FROM listings WHERE id = :id"), {"id": deleted_id}
                )
                .mappings()
                .one()
            )
            assert del_row["is_deleted"] is True
            assert del_row["price"] == orig_deleted["price"]
            assert del_row["title"] == orig_deleted["title"]
            assert (
                db.execute(
                    text("SELECT COUNT(*) FROM listing_price_history WHERE listing_id = :id"), {"id": deleted_id}
                ).scalar_one()
                == 0
            )
            assert (
                db.execute(
                    text("SELECT COUNT(*) FROM rental_estimates WHERE listing_id = :id"), {"id": deleted_id}
                ).scalar_one()
                == 0
            )

        # ── Run 3: original feed returns -> dropped_id is automatically reactivated ──
        r3 = Replayer(recording)
        with freeze_time(recorded_at), r3.patch(), mock.patch("time.sleep", return_value=None):
            app_main.scrape_city("imovirtual", "Ermesinde", "buy")

        with isolated_app_db() as db:
            reactivated_row = (
                db.execute(text("SELECT active FROM listings WHERE id = :id"), {"id": dropped_id}).mappings().one()
            )
            assert reactivated_row["active"] is True

    def test_incomplete_scrape_preserves_existing_active_listings(
        self, isolated_app_db, recording, tmp_path, monkeypatch
    ):
        """When a source blocks or errors mid-scrape, existing active listings must NOT be deactivated."""
        import curl_cffi.requests

        import main as app_main

        monkeypatch.chdir(tmp_path)
        recorded_at = recording["meta"]["recorded_at"]

        # Seed real active listings for both sources in Ermesinde
        r1 = Replayer(recording)
        with freeze_time(recorded_at), r1.patch(), mock.patch("time.sleep", return_value=None):
            app_main.scrape_city("imovirtual", "Ermesinde", "buy")
            app_main.scrape_city("era", "Ermesinde", "buy")

        with isolated_app_db() as db:
            imo_before = db.execute(
                text(
                    "SELECT COUNT(*) FROM listings WHERE source = 'imovirtual' AND city = 'Ermesinde' AND active = true"
                )
            ).scalar_one()
            era_before = db.execute(
                text("SELECT COUNT(*) FROM listings WHERE source = 'era' AND city = 'Ermesinde' AND active = true")
            ).scalar_one()
        assert imo_before >= 50
        assert era_before >= 10

        # Simulate Imovirtual failing on page 2 (partial scrape) and ERA failing on token page (0 listings)
        base_replayer = Replayer(recording)

        class FailingMidStreamSession:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, url, params=None, **kwargs):
                if "era.pt" in url:
                    return FakeResponse(503, "")
                if "page=2&" in url:
                    return FakeResponse(500, "")
                return base_replayer.respond("GET", url, params)

            def post(self, url, json=None, params=None, **kwargs):
                return FakeResponse(503, "")

        with (
            freeze_time(recorded_at),
            mock.patch.object(curl_cffi.requests, "Session", FailingMidStreamSession),
            mock.patch("time.sleep", return_value=None),
        ):
            imo_partial = app_main.scrape_city("imovirtual", "Ermesinde", "buy")
            era_failed = app_main.scrape_city("era", "Ermesinde", "buy")

        assert 0 < imo_partial["fetched"] < imo_before
        assert era_failed["fetched"] == 0

        with isolated_app_db() as db:
            imo_after = db.execute(
                text(
                    "SELECT COUNT(*) FROM listings WHERE source = 'imovirtual' AND city = 'Ermesinde' AND active = true"
                )
            ).scalar_one()
            era_after = db.execute(
                text("SELECT COUNT(*) FROM listings WHERE source = 'era' AND city = 'Ermesinde' AND active = true")
            ).scalar_one()

        assert imo_after == imo_before
        assert era_after == era_before

    def test_import_and_cli_work_without_database_url(self, tmp_path):
        clean_env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        proc_import = subprocess.run(
            [sys.executable, "-c", "import main, yieldhunter; print('ok')"],
            cwd=ROOT_DIR,
            env=clean_env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert proc_import.stdout.strip() == "ok"

        proc_help = subprocess.run(
            [sys.executable, "-m", "yieldhunter", "--help"],
            cwd=ROOT_DIR,
            env=clean_env,
            capture_output=True,
            text=True,
            check=True,
        )
        for flag in ("--source", "--type", "--city", "--parallel", "--stats-dir"):
            assert flag in proc_help.stdout
