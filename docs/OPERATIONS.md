# Operations

## Local setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # DATABASE_URL=postgresql://user:password@host:5432/db
python -m alembic upgrade head
python seed.py           # optional: two fake listings (test-1 rented, test-2 vacant)
```

## Running

```bash
python main.py                                   # imovirtual, buy, all cities sequentially
python main.py --source era --city Maia --type rent
python main.py --type buy --parallel             # thread per city
python main.py --type estimates [--city Porto]
python main.py --type contracts [--city Porto]
```

A full sequential buy scrape is slow because of the 2 s delay per request plus detail fetches. ERA buy fetches a detail page for every listing.

## Tests

```bash
python -m pytest tests/ --ignore=tests/test_integration.py   # = CI
python -m pytest tests/test_contract_extractor.py -q          # pure unit, fast
```

- `tests/conftest.py` starts `postgres:16-alpine` with **testcontainers** (Docker must be running) and builds the schema
  with `Base.metadata.create_all`. Fixtures: `db`, `clean_db` (buy tables), `clean_rental_db`, and the helpers `make_item()` /
  `make_response()` (Imovirtual item shape).
- A `DATABASE_URL` env var must exist anyway (`db/client.py` reads it at import). Any value works for tests that don't touch `Session`.
- HTTP is never hit: tests patch `scraper.<source>.fetcher.curl_requests` and `.time`.
- `test_integration.py` is excluded in CI. It runs the parse → enrich → upsert flow with mocks.

| File | Covers |
|---|---|
| `test_parser.py` | Imovirtual + ERA parsing, typology, location, city filters |
| `test_fetcher.py` | pagination, ceiling stop, buildId/token, detail bucket rotation |
| `test_repository.py` | upsert, price history, `is_deleted` guard, deactivation scoping, rented-id lookup (buy + rent) |
| `test_rental_estimates.py` | per-listing tier waterfall + bulk `refresh_rental_estimates` (deleted skip, city scope) |
| `test_contract_extractor.py` | PT/EN rent and expiry extraction cases |
| `test_normalization.py`, `test_utils.py`, `test_scrapers.py` | aliases, keyword detection, scraper wiring |
| `test_integration.py`, `test_rental_integration.py` | end-to-end with mocked HTTP |

## Lint

Ruff (`pyproject.toml`): line length 120, rules `E F W I`, migrations exempt from E501. A local `.git/hooks/pre-commit`
auto-fixes and re-stages (`.pre-commit-config.yaml` is only a comment). Manual run:
`python -m ruff check --fix . && python -m ruff format .`

## GitHub Actions

Secret: `DATABASE_URL` (Neon). Runners: `ubuntu-26.04` (test uses `ubuntu-latest`). Python 3.12, pip cache.

### `scrape.yml`: cron `0 4 * * *` (04:00 UTC) + manual dispatch
Dispatch inputs: `source` (Both/Imovirtual/ERA), `scraping_type` (""/Buy/Rent), `city` ("" = all).

| Job | Needs | Notes |
|---|---|---|
| `migrate` | — | `alembic upgrade head` |
| `scrape-buy` | migrate | matrix `source × city` (2 × 9 = 18 jobs), `fail-fast: false`, 60 min |
| `scrape-rent` | scrape-buy | same matrix. Runs if nothing failed |
| `extract-contracts` | buy, rent | `--type contracts` (all cities, single job) |
| `calculate-estimates` | buy, rent | `--type estimates` (all cities) |
| `summarise` | all | downloads `scrape-stats-*` artifacts and writes Buy / Rent / Contracts / Estimates tables to the job summary (sums both sources per city) |

> [!IMPORTANT]
> `scrape-rent`, `extract-contracts` and `calculate-estimates` use `always() && !failure()`. One failed buy matrix
> cell skips all downstream jobs for that run.

### `test.yml`: on `pull_request` + manual
Spins up a `postgres:18-alpine` service, runs `alembic upgrade head` against it (validates migrations), then pytest
(which uses its own testcontainers DB).

### `migrate.yml`: manual only
`alembic upgrade head` against prod.

## Playbooks

- **Add a city** → [SCRAPERS.md § Adding a city](SCRAPERS.md#adding-a-city)
- **Add a source** → [SCRAPERS.md § Adding a source](SCRAPERS.md#adding-a-source)
- **Schema change** → [DATA_MODEL.md § Writing a migration](DATA_MODEL.md#writing-a-migration)
- **New neighborhood spellings showing up** → add aliases to `normalization._NEIGHBORHOOD_ALIASES` (and
  `_NEIGHBORHOOD_CITY` if the city is wrong, or `_GENERIC_NEIGHBORHOODS` if it isn't a parish), add a test in
  `test_normalization.py`, and add a data migration that remaps existing rows in `listings` + `rental_listings`.
- **Too many/few rented flags** → edit `config.RENTED_KEYWORDS`. Keep in mind that `renda` / `arrendamento` are broad.
- **Imovirtual scrape returns 0** → usually the `buildId` or the `pageProps.data.searchAds` shape changed. Check
  `_get_build_id` / `_fetch_page`. A 403 means TLS impersonation needs a newer `curl_cffi`.
- **ERA scrape returns 0** → token regex or Module/Tab IDs changed. Inspect the search page HTML for `data-moduleid`.

## Known quirks / tech debt

- An empty scrape (e.g. blocked request) deactivates every listing for that source+city until the next good run.
- `run_extract_contracts` uses the Imovirtual detail endpoint even for ERA URLs (falls back to the stored description).
- `stats-*.json` outputs are not in `.gitignore`.
- `user_favorites` and `listing_snapshots` have no ORM model, so they are absent from the test schema.
- The tier logic exists twice (bulk CTE + per-listing). Keep them identical.
- `test.yml` timeout is 5 min. Testcontainers startup counts against it.
