"""One-off recorder: runs the live pipeline against a throwaway Postgres container,
saves compressed HTTP fixtures to ``tests/fixtures/http/recording.json.gz``,
and writes the golden DB + stats snapshot to ``tests/golden/baseline.json``.

Never touches production DATABASE_URL.
"""

from __future__ import annotations

import json
import os
import tempfile
import time as real_time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from freezegun import freeze_time
from testcontainers.postgres import PostgresContainer

from tests.flows.http_replay import FIXTURES_DIR, Recorder
from tests.flows.snapshot import dump_db_snapshot

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"
RECORDED_CITIES = ["Ermesinde", "Penafiel", "Maia"]
RECORDED_SOURCES = ["imovirtual", "era"]
POLITE_RECORD_DELAY = 0.35


def main() -> None:
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    real_sleep = real_time.sleep

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        db_url = pg.get_connection_url()
        os.environ["DATABASE_URL"] = db_url
        assert "neon.tech" not in os.environ["DATABASE_URL"]

        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config(str(Path(__file__).resolve().parent.parent.parent / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")

        from sqlalchemy import create_engine

        import main as app_main
        from yieldhunter.db.session import configure_session, session_scope

        configure_session(create_engine(db_url))

        recorder = Recorder()
        run_stats: list[dict] = []

        def fast_sleep(_seconds: float) -> None:
            real_sleep(POLITE_RECORD_DELAY)

        cwd_before = Path.cwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                with (
                    freeze_time(recorded_at),
                    recorder.patch(),
                    mock.patch("time.sleep", side_effect=fast_sleep),
                ):
                    for source in RECORDED_SOURCES:
                        for city in RECORDED_CITIES:
                            run_stats.append(app_main.scrape_city(source, city, "buy"))
                    for source in RECORDED_SOURCES:
                        for city in RECORDED_CITIES:
                            run_stats.append(app_main.scrape_city(source, city, "rent"))
                    contract_stats = app_main.run_extract_contracts(city=None)
                    estimate_stats = app_main.run_refresh_estimates(city=None)
            finally:
                os.chdir(cwd_before)

        with session_scope() as db:
            snapshot = dump_db_snapshot(db)

    meta = {
        "recorded_at": recorded_at,
        "cities": RECORDED_CITIES,
        "sources": RECORDED_SOURCES,
        "exchange_count": len(recorder.exchanges),
    }
    recorder.save(FIXTURES_DIR / "recording.json.gz", meta=meta)

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    golden = {
        "meta": meta,
        "scrape_stats": run_stats,
        "contract_stats": contract_stats,
        "estimate_stats": estimate_stats,
        "db": snapshot,
    }
    (GOLDEN_DIR / "baseline.json").write_text(
        json.dumps(golden, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"Recorded {len(recorder.exchanges)} HTTP exchanges -> {FIXTURES_DIR / 'recording.json.gz'}\n"
        f"Buy listings: {len(snapshot['listings'])}, "
        f"Rent listings: {len(snapshot['rental_listings'])}, "
        f"Estimates: {len(snapshot['rental_estimates'])}, "
        f"Contracts: {len(snapshot['rent_contract_details'])}"
    )


if __name__ == "__main__":
    main()
