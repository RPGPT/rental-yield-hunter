# AGENTS.md — context for AI coding sessions

Read this first. It covers what the repo does, where things live, and the rules that are easy to break.
For more detail, see [`docs/`](docs/):

| Doc | Read when… |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Changing the pipeline, CLI, repository layer, estimates, clusters, contracts, or alerts |
| [docs/SCRAPERS.md](docs/SCRAPERS.md) | Touching Imovirtual / ERA / Casa Sapo fetching or parsing, or adding a city or source |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Changing tables or columns, or writing migrations / SQL |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | CI workflows, tests, alerts setup, running locally, playbooks for common changes |
| [yieldhunter/sources/imovirtual/FILTERS.md](yieldhunter/sources/imovirtual/FILTERS.md) | Imovirtual URL / filter reverse-engineering notes |

## What this is

A Python 3.12 batch scraper & investment-analysis pipeline (`yieldhunter/`). **No web server and no frontend in this repo.** Every day it:

1. Scrapes **buy** listings (€50k–€405k) and **rental** listings (€300–€4,000/mo) for apartments in 9 Porto-area cities
   from **three sources**: `imovirtual` (imovirtual.com), `era` (era.pt), and `casasapo` (casa.sapo.pt).
2. Upserts them into Postgres (Neon in prod), tracks `initial_price`, `previous_price` on changes, cumulative price-drop
   metrics (`price_drop_amount`, `price_drop_pct`, `price_change_count`), and deactivates missing listings (gated on `result.complete`).
3. Flags buy listings that are **already tenanted** (`is_rented`) or carry a **lifetime-rent** clause (`lifetime_rent`).
4. Extracts **current rent + contract expiry** from stored descriptions (`rent_contract_details`) and computes lease-expiry
   upside metrics (`current_yield`, `reversion_yield`, `rent_upside_pct`, `months_to_expiry`).
5. Estimates **non-linear market rent and gross yield** (`rental_estimates`) via size-curved (`area^0.30`) weighted-median
   comparables over active + 60-day recently-rented listings.
6. Clusters duplicate multi-agency / cross-source buy listings (`listing_clusters`) to expose price spreads and cheapest agency.
7. Dispatches **saved-search deal alerts** (`saved_searches` + `alert_notifications`) via Telegram, Resend email, or Webhook.

A separate Angular 21 + Neon Auth frontend (different repo) reads the same DB.

## Map

```
main.py                           thin CLI shim -> yieldhunter.cli (re-exports pipeline entrypoints)
yieldhunter/
  cli.py, __main__.py             CLI (--source, --type buy|rent|estimates|contracts|clusters|alerts|summarize)
  config.py                       price bounds, delays, SUPPORTED_CITIES, PARISH_CITIES, estimate parameters
  db/
    session.py                    lazy engine + session_scope() + configure_session() for tests
    models.py                     SQLAlchemy models (full parity with Alembic 0001..0030)
    repository/
      common.py                   chunks() (500 rows), sanitize_url()
      listings.py                 generic _upsert (+ initial_price / price_drop_* tracking), _deactivate_missing
      estimates.py                size-curved weighted-median estimator (area^0.30 + 60d recency)
      contracts.py                rented-listing + raw_data query, contract upsert + lease-upside sync
      clusters.py                 refresh_listing_clusters (multi-agency & cross-source dedup)
      alerts.py                   saved-search evaluation & alert_notifications deduplication
  analysis/
    normalization.py              normalize_location(): freguesia aliases -> canonical names
    rented.py                     is_rented() (compiled keyword regex), is_lifetime_rent()
    typology.py                   shared T-number helpers (word2number, int, title regex)
    contracts.py                  deterministic PT/EN rent + contract-expiry extractor (no LLM)
    clustering.py                 union-find physical apartment clustering & floor/street normalization
    alerts.py                     saved-search filter matcher & Markdown digest formatter
  sources/
    base.py, http.py, registry.py Scraper ABC, ScrapeResult(listings, complete), source registry
    imovirtual/                   Next.js _next/data client, parser, constants, scrapers, FILTERS.md
    era/                          CSRF token + JSON API client, parser, constants, scrapers
    casasapo/                     HTML + embedded schema.org JSON-LD client, parser, constants, scrapers
  pipeline/
    scrape.py, estimates.py, contracts.py, clusters.py, alerts.py, stats.py
migrations/versions/              Alembic, revisions "0001"…"0030" (linear, zero-padded string IDs)
tests/                            unit + integration tests + tests/flows/ (real recorded HTTP + golden DB)
.github/workflows/                scrape.yml (daily 04:00 UTC), test.yml (PRs), migrate.yml (manual)
```

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env                                            # DATABASE_URL=postgresql://...
python -m alembic upgrade head
python -m yieldhunter --source casasapo --city Porto --type buy
python -m yieldhunter --type clusters                           # or estimates | contracts | alerts | summarize
python -m pytest tests/ -v                                      # unit + real-data flow tests (needs Docker)
python -m ruff check --fix . && python -m ruff format .         # line-length 120, rules E,F,W,I
```

## Invariants and gotchas (don't break these)

- **`is_deleted` is sacred.** Upserts use `ON CONFLICT … WHERE is_deleted = false`, and deleted rows get neither raw-data
  refreshes nor deactivation, estimates, clustering, or contract extraction.
- **Deactivation is scoped by `source` AND `city`, and gated on `result.complete`.** Never deactivate if a scrape errored
  mid-pagination, hit persistent 429s, or failed token/buildId retrieval.
- **Price history records changes only (with `previous_price`), while `initial_price` is immutable.** New listings get
  `initial_price = price` and 0 history rows; subsequent price changes record `(previous_price, price)` in history and
  update `price_drop_amount`, `price_drop_pct`, and `price_change_count`.
- **Chunk bulk inserts** with `chunks()` (500 rows) to stay under Postgres's 65,535 bind-parameter limit.
- **Neighborhood normalization happens inside `_upsert`.** Parsers emit raw names. If you add aliases to
  `yieldhunter/analysis/normalization.py`, add a data migration remapping existing rows (see 0025–0027).
- **`city` for Ermesinde/Alfena** is the parish name, not "Valongo" (`config.PARISH_CITIES`).
- **IDs:** Imovirtual = numeric ad id; ERA = `"era-" + Reference`; Casa Sapo = `"casasapo-" + UUID`. All share PK space.
- **URLs:** `/hpr/` is stripped (in the parser and again at upsert).
- **Detail enrichment:** Imovirtual rotates full-description fetches weekly (+ all known/flagged rented IDs); ERA enriches
  every buy listing; Casa Sapo includes full untruncated `.property-description` directly on search pages (no detail HTTP needed).
- **Contract extraction & upside sync:** `sync_contract_upside_metrics` runs at the end of both `run_extract_contracts` and
  `refresh_rental_estimates` so `current_yield`, `reversion_yield`, `rent_upside_pct`, and `months_to_expiry` stay in sync.
- **Models vs migrations:** keep `yieldhunter/db/models.py` and `migrations/versions/` in 100% parity.
