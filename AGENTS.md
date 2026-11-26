# AGENTS.md — context for AI coding sessions

Read this first. It covers what the repo does, where things live, and the rules that are easy to break.
For more detail, see [`docs/`](docs/):

| Doc | Read when… |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Changing the pipeline, CLI, repository layer, estimates or contract extraction |
| [docs/SCRAPERS.md](docs/SCRAPERS.md) | Touching Imovirtual / ERA fetching or parsing, or adding a city or source |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Changing tables or columns, or writing migrations / SQL |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | CI workflows, tests, running locally, playbooks for common changes |
| [yieldhunter/sources/imovirtual/FILTERS.md](yieldhunter/sources/imovirtual/FILTERS.md) | Imovirtual URL / filter reverse-engineering notes |

## What this is

A Python 3.12 batch scraper (`yieldhunter/`). **No web server and no frontend in this repo.** Every day it:

1. Scrapes **buy** listings (€50k–€405k) and **rental** listings (€300–€4,000/mo) for apartments in 9 Porto-area cities
   from **two sources**: `imovirtual` (imovirtual.com) and `era` (era.pt).
2. Upserts them into Postgres (Neon in prod), records price changes, and deactivates listings that have disappeared
   (only when the scrape completed without HTTP/token failures).
3. Flags buy listings that are **already tenanted** (`is_rented`) or carry a **lifetime-rent** clause (`lifetime_rent`).
4. Extracts **current rent + contract expiry** from stored descriptions of tenanted listings (`rent_contract_details`).
5. Estimates **market rent and gross yield** for each buy listing from comparable rentals (`rental_estimates`).

A separate Angular 21 + Neon Auth frontend (different repo) reads the same DB. It owns the `user_*`, `audit_log` and
`saved_searches` tables; this repo holds their models and migrations.

## Map

```
main.py                           thin CLI shim -> yieldhunter.cli (re-exports pipeline entrypoints)
yieldhunter/
  cli.py, __main__.py             CLI (--source, --type buy|rent|estimates|contracts|summarize, --city, --parallel)
  config.py                       price bounds, REQUEST_DELAY, SUPPORTED_CITIES, PARISH_CITIES, RENTED_KEYWORDS
  db/
    session.py                    lazy engine + session_scope() + configure_session() for tests
    models.py                     SQLAlchemy models (full parity with Alembic 0001..0029)
    repository/
      common.py                   chunks() (500 rows), sanitize_url()
      listings.py                 generic _upsert, _deactivate_missing, rented-ID lookup
      estimates.py                unified 4-tier CTE waterfall (bulk + per-listing)
      contracts.py                rented-listing + raw_data query, contract-detail upsert
  analysis/
    normalization.py              normalize_location(): freguesia aliases -> canonical names
    rented.py                     is_rented() (compiled keyword regex), is_lifetime_rent()
    typology.py                   shared T-number helpers (word2number, int, title regex)
    contracts.py                  deterministic PT/EN rent + contract-expiry extractor (no LLM)
  sources/
    base.py, http.py, registry.py Scraper ABC, ScrapeResult(listings, complete), source registry
    imovirtual/                   Next.js _next/data client, parser, constants, scrapers, FILTERS.md
    era/                          CSRF token + JSON API client, parser, constants, scrapers
  pipeline/
    scrape.py                     scrape_city (skips deactivation if incomplete), scrape_all
    estimates.py                  run_refresh_estimates
    contracts.py                  run_extract_contracts (DB-first using stored fullDescription)
    stats.py                      stats-*.json writer + stdlib-only CI Markdown summary renderer
migrations/versions/              Alembic, revisions "0001"…"0029" (linear, zero-padded string IDs)
tests/                            unit + integration tests + tests/flows/ (real recorded HTTP + golden DB)
.github/workflows/                scrape.yml (daily 04:00 UTC), test.yml (PRs), migrate.yml (manual)
```

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env                                            # DATABASE_URL=postgresql://...
python -m alembic upgrade head
python -m yieldhunter --source imovirtual --city Porto --type buy
python main.py --source era --type rent --parallel              # main.py shim works identically
python -m pytest tests/ -v                                      # unit + real-data flow tests (needs Docker)
python -m ruff check --fix . && python -m ruff format .         # line-length 120, rules E,F,W,I
```

`DATABASE_URL` is loaded lazily on first DB access, so importing `yieldhunter` / `main` or running pure unit tests does
not require `DATABASE_URL`.

## Invariants and gotchas (don't break these)

- **`is_deleted` is sacred.** Upserts use `ON CONFLICT … WHERE is_deleted = false`, and deleted rows get neither raw-data
  refreshes nor deactivation, estimates, or contract extraction. Users set this flag from the frontend.
- **Deactivation is scoped by `source` AND `city`, and gated on `result.complete`.** CI runs one job per `(source, city)`
  in parallel, so always pass `city=` to `deactivate_missing*`. Never deactivate if a scrape errored mid-pagination or failed
  token/buildId retrieval. A listing that reappears is reactivated automatically.
- **Price history records changes only.** A new listing gets no history row, and neither does a deleted one.
- **Chunk bulk inserts** with `chunks()` (500 rows). Postgres allows at most 65,535 bind params per statement.
- **Neighborhood normalization happens inside `_upsert`.** Parsers emit raw names. If you add aliases to
  `yieldhunter/analysis/normalization.py`, add a data migration that remaps existing rows (see 0025–0027).
- **`city` for Ermesinde/Alfena** is the parish name, not "Valongo" (`config.PARISH_CITIES`). Parsers filter on parish.
- **Imovirtual typology:** `roomsNumber` counts the kitchen/living room, so `"THREE"` → `T2` (n − 1). If it's missing,
  we fall back to a `T\d` regex on the title.
- **IDs:** Imovirtual uses its numeric ad id; ERA uses `"era-" + Reference`. Both share the `listings` PK space.
- **URLs:** `/hpr/` is stripped (in the parser and again at upsert).
- **Imovirtual detail scans are rate-bounded.** Each buy listing gets a full-description fetch once a week (`sha256(id) % 7`
  vs today's ordinal % 7), plus every listing already flagged rented or in `known_rented_ids`. ERA fetches details for every
  buy listing. Both reuse the search session and `buildId`/CSRF token.
- **Contract extraction is DB-first.** `run_extract_contracts` reads `listings.description` + `raw_data.raw_json['fullDescription']`
  directly from Postgres without redundant HTTP requests (only backfilling over HTTP if an Imovirtual row lacks `fullDescription`).
- **Rental scrapers have no enrich step** and never set `is_rented`.
- **Models vs migrations:** tests build the schema with `Base.metadata.create_all` (and `tests/flows/` runs real Alembic
  migrations). Keep `yieldhunter/db/models.py` and `migrations/versions/` in sync.
- **Polite scraping:** `REQUEST_DELAY = 2.0`s between requests. `curl_cffi` with `impersonate="chrome"` is required.

## Conventions

- Commit messages: short imperative summary (`Add …`, `fix: …`). Push straight to `main` (no PR flow in practice).
- New migration: copy the style of `0028_audit_log.py`. Set `revision = "00NN"` and `down_revision` = the previous one.
  The filename is `00NN_slug.py`. Prefer idempotent SQL (`IF NOT EXISTS`).
- Logging uses `logging.getLogger(__name__)` with `%`-style args. No prints in library code.
- Network unit tests patch `yieldhunter.sources.<source>.client.curl_requests` and `.time`; full-pipeline flow tests in
  `tests/flows/` replay real recorded HTTP exchanges from `tests/fixtures/http/recording.json.gz`.
