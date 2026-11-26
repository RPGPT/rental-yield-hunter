# Operations

## Local setup

```bash
uv venv -p 3.12 .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # DATABASE_URL=postgresql://user:password@host:5432/db
python -m alembic upgrade head
python seed.py           # optional: two fake listings (test-1 rented, test-2 vacant)
```

## Running

```bash
python -m yieldhunter                                    # imovirtual, buy, all cities sequentially
python -m yieldhunter --source era --city Maia --type rent
python -m yieldhunter --type buy --parallel              # thread per city
python -m yieldhunter --type estimates [--city Porto]
python -m yieldhunter --type contracts [--city Porto]
python -m yieldhunter --type summarize --stats-dir .
```

`python main.py …` accepts the exact same flags. `stats-*.json` files are gitignored.

## Tests

```bash
python -m pytest tests/ -v                     # full suite: unit + integration + real-data flow tests
python -m pytest tests/flows/ -v               # recorded real-data pipeline & lifecycle tests only
python -m pytest tests/test_contract_extractor.py -q   # pure unit, no Docker needed
```

- `DATABASE_URL` is **not** required to import the package or run tests (`yieldhunter/db/session.py` is lazy).
- `tests/conftest.py` starts `postgres:16-alpine` (`driver="psycopg"`) via **testcontainers** (Docker required) and
  creates the schema from `yieldhunter.db.models.Base`.
- `tests/flows/` creates a separate `flow_test` database migrated via **real Alembic (`0001` → `head`)** and replays
  real recorded HTTP responses from `tests/fixtures/http/recording.json.gz` (`Ermesinde`, `Penafiel`, `Maia` across both
  sources) against the golden DB snapshot in `tests/golden/baseline.json`, plus multi-run mutations (price changes,
  city/source-scoped deactivation, reactivation, `is_deleted` guard, and incomplete-scrape safety).
- To re-record fixtures from live sites against a throwaway container DB (never prod): `python -m tests.flows.record`.

## Lint

Ruff (`pyproject.toml`): line length 120, rules `E F W I`, migrations exempt from `E501`.
Manual run: `python -m ruff check --fix . && python -m ruff format .`

## GitHub Actions

Secret: `DATABASE_URL` (Neon).

- **`scrape.yml`** (cron `0 4 * * *` + manual dispatch): `migrate` → `scrape-buy` (matrix `source × city`) →
  `scrape-rent` → `extract-contracts` + `calculate-estimates` → `summarise` (`python3 -m yieldhunter.pipeline.stats stats`).
- **`test.yml`** (PRs + manual): runs `alembic upgrade head` on a service Postgres container, then runs the full
  `python -m pytest tests/ -v` suite.
- **`migrate.yml`** (manual): `alembic upgrade head` against prod.

## Playbooks

- **Add a city** → [SCRAPERS.md § Adding a city](SCRAPERS.md#adding-a-city)
- **Add a source** → [SCRAPERS.md § Adding a source](SCRAPERS.md#adding-a-source)
- **Schema change** → [DATA_MODEL.md § Writing a migration](DATA_MODEL.md#writing-a-migration)
- **New neighborhood spellings** → add aliases to `yieldhunter/analysis/normalization.py`, add tests in
  `tests/test_normalization.py`, and add a data migration remapping existing rows in `listings` + `rental_listings`.
- **Imovirtual / ERA scrape returns 0** → check `_get_build_id` / `_get_token`; incomplete scrapes automatically skip
  deactivating existing active listings until scraping recovers.
