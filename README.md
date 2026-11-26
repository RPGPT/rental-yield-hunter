# Rental Yield Hunter

Daily scraper for Porto-area apartment listings on **imovirtual.com** and **era.pt**. It tracks buy and rental listings
separately, records price history, flags already-tenanted properties, extracts their current rent and contract expiry,
and estimates the market rent and gross yield of every buy listing from comparable rentals.

> Working on this repo with an AI agent? Start with [AGENTS.md](AGENTS.md). Deeper docs live in [docs/](docs/).

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| HTTP | `curl_cffi` (Chrome TLS-fingerprint impersonation, gets past bot detection) |
| ORM / Migrations | SQLAlchemy + Alembic |
| Parsing helpers | `word2number` (typology), `dateparser` (contract expiry) |
| Database | PostgreSQL: Neon (prod) / testcontainers (tests) |
| CI / CD | GitHub Actions: test (PRs), scrape (daily), migrate (manual) |
| Frontend | Angular 21 + Neon Auth (separate repo, reads the same DB) |

## Coverage

- **Sources:** Imovirtual, ERA
- **Cities:** Porto · Matosinhos · Vila Nova de Gaia · Maia · Paços de Ferreira · Penafiel · Paredes · Ermesinde · Alfena
  (Ermesinde and Alfena are Valongo parishes, stored as their own city)
- **Price bands:** buy €50k–€405k · rent €300–€4,000/month (`config.py`)

## How it works

```
scrape buy (source × city) ─▶ scrape rent (source × city) ─┬─▶ extract contract details (rented buy listings)
                                                           └─▶ refresh rental estimates  (buy listings)
```

1. **Scrape.** Each scraper runs `fetch → parse → enrich`. Results are sorted by price ascending, and pagination stops at the price ceiling.
2. **Upsert.** Neighborhoods are normalised to official freguesias. Price changes go to history, raw JSON is kept, and listings
   missing from the run are marked inactive (scoped to source + city).
3. **Rented detection.** Keyword match on title and description (`arrendado`, `inquilino`, …). Imovirtual buy listings get a
   full-description check on a weekly rotation (always for already-rented ones). ERA buy listings are always checked.
4. **Contract extraction.** Regex + `dateparser` pull the current rent and contract expiry out of PT/EN descriptions. No LLM.
5. **Rental estimates.** A 4-tier comparable waterfall (typology + neighborhood/city, ±15% area, ≥3 samples) gives the
   estimated rent, confidence and gross yield.

## Structure

```
rental-yield-hunter/
├── AGENTS.md                    # context for AI coding sessions
├── docs/                        # ARCHITECTURE, SCRAPERS, DATA_MODEL, OPERATIONS
├── config.py                    # price limits, cities, parish cities, rented keywords, request delay
├── main.py                      # CLI: --source, --type buy|rent|estimates|contracts, --city, --parallel
├── normalization.py             # neighborhood → canonical freguesia / city
├── seed.py                      # seed two test listings
├── scraper/
│   ├── base.py                  # Scraper ABC (fetch → parse → enrich → run)
│   ├── utils.py                 # is_rented / is_lifetime_rent
│   ├── contract_extractor.py    # rent + expiry extraction
│   ├── imovirtual/              # Next.js data API scraper (+ FILTERS.md)
│   └── era/                     # ERA JSON API scraper
├── db/
│   ├── client.py                # engine + Session (DATABASE_URL)
│   ├── models.py                # ORM models
│   └── repository.py            # upserts, deactivation, rental estimates, contract details
├── migrations/versions/         # Alembic 0001 → 0029
├── tests/                       # pytest (testcontainers Postgres, mocked HTTP)
└── .github/workflows/           # test.yml, scrape.yml, migrate.yml
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
python3 main.py                                        # Imovirtual, buy, all cities
python3 main.py --city Porto                           # single city
python3 main.py --source era --type rent               # ERA rentals
python3 main.py --parallel                             # all cities in a thread pool
python3 main.py --type estimates [--city Maia]         # recompute rental estimates / yields
python3 main.py --type contracts [--city Maia]         # extract rent + expiry for rented listings
```

Each run writes a `stats-*.json` file that CI uses for the run summary.

## Tests

Docker is required (testcontainers starts a throwaway Postgres). `DATABASE_URL` must be set to any value.

```bash
python3 -m pytest tests/ --ignore=tests/test_integration.py   # same as CI
python3 -m ruff check --fix . && python3 -m ruff format .      # lint / format
```

## GitHub Actions

| Workflow | Trigger | What it does |
|---|---|---|
| `scrape.yml` | daily 04:00 UTC + manual (source / type / city inputs) | migrate → buy matrix (source × city) → rent matrix → contracts + estimates → Markdown summary |
| `test.yml` | pull requests + manual | `alembic upgrade head` on a service DB, then pytest |
| `migrate.yml` | manual | `alembic upgrade head` on prod |

Required repository secret: `DATABASE_URL`.

## Schema

| Table | Purpose |
|---|---|
| `listings` | Buy listings (PK = source listing id; ERA ids are `era-…`). Includes `is_rented`, `lifetime_rent` |
| `listing_price_history` | Every buy price change |
| `raw_data` | Latest raw API JSON per buy listing |
| `rental_listings` | Rental listings (adds `rent_price_per_m2`) |
| `rental_listing_price_history` / `rental_raw_data` | Same as above, for rentals |
| `rental_estimates` | Estimated rent, €/m², sample count, confidence, match level, gross yield per buy listing |
| `rent_contract_details` | Extracted current rent and contract expiry for tenanted buy listings |
| `user_favorites`, `user_hidden`, `saved_searches`, `audit_log` | Frontend user data (`user_id` = `neon_auth.users.id`, enforced in app code) |

Full column reference: [docs/DATA_MODEL.md](docs/DATA_MODEL.md).

## Key behaviours

- **`is_deleted` guard:** a listing deleted from the frontend is never overwritten by scrape data, even if it reappears.
- **City-scoped deactivation:** `deactivate_missing` only touches rows of the same source and city, so parallel jobs
  can't interfere with each other. Listings that reappear are reactivated.
- **Neighborhood normalization:** aliases and landmarks are mapped to official freguesias (union-parish names). Generic names
  fall back to the city.
- **Typology mapping:** Imovirtual `roomsNumber` (`THREE`) → `T2` (rooms − 1). ERA `Rooms` → `T{n}`. Title regex as a
  fallback.
- **Lifetime rent detection:** accent-insensitive search for `vitalício/vitalícia` in short + full descriptions.
- **URL sanitisation:** `/hpr/` segments are stripped from all URLs.

## Disclaimer

For personal and educational use only. Respect rate limits.
