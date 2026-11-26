# Rental Yield Hunter

Daily scraper and yield analyzer for Porto-area apartment listings on **imovirtual.com** and **era.pt**. Tracks buy and
rental listings separately, records price history, flags already-tenanted properties, extracts their current rent and
contract expiry, and estimates the market rent and gross yield of every buy listing from comparable rentals.

> Working on this repo with an AI agent? Start with [AGENTS.md](AGENTS.md). Deeper docs live in [docs/](docs/).

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 (`yieldhunter` package) |
| HTTP | `curl_cffi` (Chrome TLS-fingerprint impersonation) |
| ORM / Migrations | SQLAlchemy + Alembic (`0001` → `0029`) |
| Parsing helpers | `word2number` (typology), `dateparser` (contract expiry) |
| Database | PostgreSQL: Neon (prod) / testcontainers (tests) |
| CI / CD | GitHub Actions: `test.yml` (PRs), `scrape.yml` (daily 04:00 UTC), `migrate.yml` (manual) |
| Frontend | Angular 21 + Neon Auth (separate repo, reads the same DB) |

## Coverage

- **Sources:** Imovirtual, ERA
- **Cities:** Porto · Matosinhos · Vila Nova de Gaia · Maia · Paços de Ferreira · Penafiel · Paredes · Ermesinde · Alfena
  (Ermesinde and Alfena are Valongo parishes, stored under their own city name)
- **Price bands:** buy €50k–€405k · rent €300–€4,000/month (`yieldhunter/config.py`)

## How it works

```
scrape buy (source × city) ─▶ scrape rent (source × city) ─┬─▶ extract contract details (stored descriptions)
                                                           └─▶ refresh rental estimates  (4-tier CTE waterfall)
```

1. **Scrape (`yieldhunter/sources/`).** Each scraper runs `fetch → parse → enrich` while reusing a single HTTP session and
   `buildId`/CSRF token. Results are sorted by price ascending and stop at the price ceiling.
2. **Upsert & safe deactivation (`yieldhunter/db/repository/listings.py`).** Neighborhoods are normalized to official
   freguesias, price changes go to history, and missing listings are marked inactive (scoped to `source + city`, and
   skipped automatically if a scrape was incomplete).
3. **Rented detection (`yieldhunter/analysis/rented.py`).** Keyword match on title and description (`arrendado`,
   `inquilino`, …) plus accent-insensitive lifetime-rent (`vitalício/a`) detection. Imovirtual buy listings rotate detail
   scans weekly (always refreshing known-rented IDs); ERA buy listings enrich every listing.
4. **Contract extraction (`yieldhunter/pipeline/contracts.py`).** Deterministic regex + `dateparser` extraction over the
   already-stored full descriptions in Postgres (zero redundant HTTP calls).
5. **Rental estimates (`yieldhunter/db/repository/estimates.py`).** Single 4-tier PostgreSQL CTE waterfall
   (typology + neighborhood/city, ±15% area, ≥3 samples) computing estimated monthly rent, confidence, and gross yield.

## Structure

```
rental-yield-hunter/
├── AGENTS.md                        # quickstart context for AI coding sessions
├── docs/                            # ARCHITECTURE, SCRAPERS, DATA_MODEL, OPERATIONS
├── main.py                          # thin CLI shim -> yieldhunter.cli
├── seed.py                          # seed two local test listings
├── yieldhunter/
│   ├── cli.py, __main__.py          # CLI (--source, --type, --city, --parallel, --stats-dir)
│   ├── config.py                    # price bounds, cities, parish cities, delay, keywords
│   ├── db/                          # lazy session_scope(), ORM models, chunked repositories
│   ├── analysis/                    # normalization, rented/lifetime flags, typology, contract extractor
│   ├── sources/                     # Scraper ABC, ScrapeResult, Imovirtual & ERA clients/parsers
│   └── pipeline/                    # scrape, estimates, contracts, CI Markdown summary renderer
├── migrations/versions/             # Alembic 0001 → 0029
├── tests/                           # unit tests + tests/flows/ (recorded real HTTP + golden snapshots)
└── .github/workflows/               # test.yml, scrape.yml, migrate.yml
```

## Setup

```bash
git clone https://github.com/RPGPT/rental-yield-hunter.git
cd rental-yield-hunter
cp .env.example .env            # set DATABASE_URL
pip install -r requirements.txt
python3 -m alembic upgrade head
```

## Usage

```bash
python3 -m yieldhunter                                  # Imovirtual, buy, all cities (or `python3 main.py`)
python3 -m yieldhunter --city Porto                     # single city
python3 -m yieldhunter --source era --type rent         # ERA rentals
python3 -m yieldhunter --parallel                       # all cities in a thread pool
python3 -m yieldhunter --type estimates [--city Maia]   # recompute rental estimates / yields
python3 -m yieldhunter --type contracts [--city Maia]   # extract rent + expiry for rented listings
python3 -m yieldhunter --type summarize --stats-dir .   # render Markdown run summary
```

## Tests & Linting

Docker is required (testcontainers starts an isolated Postgres instance). `DATABASE_URL` does not need to be set.

```bash
python3 -m pytest tests/ -v
python3 -m ruff check --fix . && python3 -m ruff format .
```

## GitHub Actions

| Workflow | Trigger | What it does |
|---|---|---|
| `scrape.yml` | daily 04:00 UTC + manual (source / type / city inputs) | migrate → buy matrix (source × city) → rent matrix → contracts + estimates → Markdown summary |
| `test.yml` | pull requests + manual | `alembic upgrade head` on a service DB, then full `pytest tests/ -v` |
| `migrate.yml` | manual | `alembic upgrade head` on prod |

Required repository secret: `DATABASE_URL`.

## Schema

| Table | Purpose |
|---|---|
| `listings` | Buy listings (PK = source listing id; ERA ids are `era-…`). Includes `is_rented`, `lifetime_rent` |
| `listing_price_history` / `raw_data` | Buy price change history and latest raw API JSON |
| `rental_listings` | Rental listings (adds `rent_price_per_m2`) |
| `rental_listing_price_history` / `rental_raw_data` | Rental price change history and latest raw API JSON |
| `rental_estimates` | Estimated rent, €/m², sample count, confidence, match level, gross yield per buy listing |
| `rent_contract_details` | Extracted current rent and contract expiry for tenanted buy listings |
| `user_favorites`, `user_hidden`, `saved_searches`, `audit_log`, `listing_snapshots` | Frontend user & archival tables |

Full column reference: [docs/DATA_MODEL.md](docs/DATA_MODEL.md).

## Disclaimer

For personal and educational use only. Respect rate limits.
