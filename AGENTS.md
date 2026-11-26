# AGENTS.md — context for AI coding sessions

Read this first. It covers what the repo does, where things live, and the rules that are easy to break.
For more detail, see [`docs/`](docs/):

| Doc | Read when… |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Changing the pipeline, CLI, repository layer, estimates or contract extraction |
| [docs/SCRAPERS.md](docs/SCRAPERS.md) | Touching Imovirtual / ERA fetching or parsing, or adding a city or source |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Changing tables or columns, or writing migrations / SQL |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | CI workflows, tests, running locally, playbooks for common changes |
| [scraper/imovirtual/FILTERS.md](scraper/imovirtual/FILTERS.md) | Imovirtual URL / filter reverse-engineering notes |

## What this is

A Python 3.12 batch scraper. **No web server and no frontend in this repo.** Every day it:

1. Scrapes **buy** listings (€50k–€405k) and **rental** listings (€300–€4,000/mo) for apartments in 9 Porto-area cities
   from **two sources**: `imovirtual` (imovirtual.com) and `era` (era.pt).
2. Upserts them into Postgres (Neon in prod), records price changes, and deactivates listings that have disappeared.
3. Flags buy listings that are **already tenanted** (`is_rented`) or carry a **lifetime-rent** clause (`lifetime_rent`).
4. Extracts **current rent + contract expiry** from the descriptions of tenanted listings (`rent_contract_details`).
5. Estimates **market rent and gross yield** for each buy listing from comparable rentals (`rental_estimates`).

A separate Angular 21 + Neon Auth frontend (different repo) reads the same DB. It owns the `user_*`, `audit_log` and
`saved_searches` tables; this repo only holds their migrations.

## Map

```
main.py                 CLI + orchestration (scrape_city, run_refresh_estimates, run_extract_contracts)
config.py               price bounds, REQUEST_DELAY, SUPPORTED_CITIES, PARISH_CITIES, RENTED_KEYWORDS
normalization.py        normalize_location(): freguesia aliases → canonical names, applied at upsert
scraper/base.py         Scraper ABC: run() = enrich(parse(fetch()))
scraper/utils.py        is_rented() (keyword match), is_lifetime_rent() (accent-insensitive "vitalici[ao]")
scraper/contract_extractor.py  regex + dateparser → current rent / contract expiry (no LLM)
scraper/imovirtual/     Next.js _next/data JSON scraping (buildId) — fetcher, parser, constants
scraper/era/            ERA JSON API (CSRF token + ModuleId/TabId headers) — fetcher, parser, constants
db/client.py            engine + Session (reads DATABASE_URL at import time)
db/models.py            SQLAlchemy models (source of truth for test schema)
db/repository.py        generic _upsert, _deactivate_missing, rental-estimate CTE, contract upsert
migrations/versions/    Alembic, revisions "0001"…"0029" (linear, zero-padded string IDs)
tests/                  pytest; Postgres via testcontainers (Docker needed); HTTP is mocked
.github/workflows/      scrape.yml (daily 04:00 UTC), test.yml (PRs), migrate.yml (manual)
```

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env                      # DATABASE_URL=postgresql://...
python -m alembic upgrade head
python main.py --source imovirtual --city Porto --type buy     # --type buy|rent|estimates|contracts
python main.py --source era --type rent --parallel             # all cities, one thread per city
python -m pytest tests/ --ignore=tests/test_integration.py     # what CI runs (needs Docker)
python -m ruff check --fix . && python -m ruff format .        # line-length 120, rules E,F,W,I
```

`DATABASE_URL` must be set even for unit tests: `db/client.py` reads it at import time, and `main.py` imports it.

## Invariants and gotchas (don't break these)

- **`is_deleted` is sacred.** Upserts use `ON CONFLICT … WHERE is_deleted = false`, and deleted rows get neither raw-data
  refreshes nor deactivation. Users set this flag from the frontend.
- **Deactivation is scoped by `source` AND `city`.** CI runs one job per (source, city) in parallel, so always pass
  `city=` to `deactivate_missing*`. A listing that reappears is reactivated automatically.
- **Price history records changes only.** A new listing gets no history row, and neither does a deleted one.
- **Chunk bulk inserts** with `_chunks()` (500 rows). Postgres allows at most 65,535 bind params per statement.
- **Neighborhood normalization happens inside `_upsert`.** Parsers emit raw names. If you add aliases to
  `normalization.py`, add a data migration that remaps existing rows (see 0025–0027).
- **`city` for Ermesinde/Alfena** is the parish name, not "Valongo" (`config.PARISH_CITIES`). Parsers filter on parish.
- **Imovirtual typology:** `roomsNumber` counts the kitchen/living room, so `"THREE"` → `T2` (n − 1). If it's missing,
  we fall back to a `T\d` regex on the title.
- **IDs:** Imovirtual uses its numeric ad id; ERA uses `"era-" + Reference`. Both share the `listings` PK space.
- **URLs:** `/hpr/` is stripped (in the parser and again at upsert).
- **Imovirtual detail scans are rate-bounded.** Each buy listing gets a full-description fetch once a week (sha256(id) % 7
  vs today's ordinal % 7), plus every listing already flagged rented or in `known_rented_ids`. ERA fetches details for every buy listing.
- **Rental scrapers have no enrich step** and never set `is_rented`.
- **Models vs migrations:** tests build the schema with `Base.metadata.create_all`, while prod uses Alembic. Keep both
  in sync. `user_favorites` and `listing_snapshots` exist in prod but have **no model**.
- **Polite scraping:** `REQUEST_DELAY = 2`s between requests. `curl_cffi` with `impersonate="chrome"` is required, because
  plain `requests` gets bot-blocked.
- Running `main.py` writes `stats-*.json` into the CWD (CI uploads them as artifacts). They are not gitignored, so don't commit them.

## Conventions

- Commit messages: short imperative summary (`Add …`, `fix: …`). Push straight to `main` (no PR flow in practice).
- New migration: copy the style of `0028_audit_log.py`. Set `revision = "00NN"` and `down_revision` = the previous one.
  The filename is `00NN_slug.py`. Prefer idempotent SQL (`IF NOT EXISTS`).
- Logging uses `logging.getLogger(__name__)` with `%`-style args. No prints.
- Network code is tested with `unittest.mock.patch` on `<module>.curl_requests` and `<module>.time`. See `tests/test_fetcher.py`.
