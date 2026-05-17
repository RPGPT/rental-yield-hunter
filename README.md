# Rental Yield Hunter

Daily scraper for Porto-area apartment listings on imovirtual.com. Tracks buy listings and rental listings separately, records price history, flags tenanted properties, and surfaces investment opportunities.

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| HTTP | `curl_cffi` (TLS-fingerprint spoofing, bypasses bot detection) |
| ORM / Migrations | SQLAlchemy + Alembic |
| Database | PostgreSQL — Neon (prod) / Docker testcontainers (tests) |
| CI / CD | GitHub Actions — test, scrape (daily matrix), migrate (manual) |
| Frontend | Angular 21 + Neon Auth (separate repo) |

## Cities

Porto · Matosinhos · Vila Nova de Gaia · Maia

## Structure

```
rental-yield-hunter/
├── config.py                    # price limits, supported cities, rented keywords
├── main.py                      # CLI entry point (--source, --city, --type, --parallel)
├── seed.py                      # seed test data
├── scraper/
│   ├── base.py                  # Scraper ABC  (fetch → parse → enrich → run)
│   ├── utils.py                 # shared helpers (is_rented keyword detection)
│   └── imovirtual/
│       ├── __init__.py          # ImovirtualBuyScraper, ImovirtualRentalScraper
│       ├── constants.py         # CITY_PATHS, ESTATE_MAP
│       ├── fetcher.py           # HTTP + pagination + detail enrichment
│       └── parser.py            # JSON → normalised dicts, typology mapping
├── db/
│   ├── client.py                # engine + Session factory
│   ├── models.py                # all ORM models (see Schema below)
│   └── repository.py           # upsert_listings, upsert_rental_listings,
│                                # deactivate_missing, price history
├── migrations/versions/         # 0001 → 0019 Alembic migrations
├── tests/
│   └── ...
└── .github/workflows/
    ├── test.yml                 # runs on every PR
    ├── scrape.yml               # daily matrix (one runner per city) + manual trigger
    └── migrate.yml              # manual-only: alembic upgrade head
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
# Scrape all cities, buy listings (default)
python3 main.py

# Single city
python3 main.py --city Porto

# Rental listings
python3 main.py --type rent

# All cities in parallel (thread pool)
python3 main.py --parallel

# Explicit source
python3 main.py --source imovirtual --city Maia --type buy
```

## Tests

Requires Docker (testcontainers spins up a throwaway Postgres instance).

```bash
pytest
```

## GitHub Actions

### `scrape.yml` — daily at 07:00 UTC
- **Matrix job** — each city gets its own runner, all four run in parallel.
- Buy and rental listings scraped separately.
- On finish, a `summarise` job prints a Markdown table to the Actions run summary:

| City | Fetched | Rented | Price changes |
|---|---:|---:|---:|
| Maia | … | … | … |
| Porto | … | … | … |
| … | | | |
| **Total** | **…** | **…** | **…** |

### `migrate.yml` — manual only
Runs `alembic upgrade head` against the production database.

### `test.yml` — every PR
Full pytest suite with testcontainers.

Required repository secret: `DATABASE_URL`

## Schema

### Buy listings

| Table | Purpose |
|---|---|
| `listings` | All buy listings (€50k–€405k). PK = listing ID from Imovirtual. |
| `listing_price_history` | Every price change recorded per listing. |
| `raw_data` | Raw API JSON snapshot per listing. |
| `listing_snapshots` | Blob URL of rendered page snapshot (for archival). |

### Rental listings

| Table | Purpose |
|---|---|
| `rental_listings` | All rental listings (€300–€4000/mo). Same structure as `listings`. |
| `rental_listing_price_history` | Price change log for rentals. |
| `rental_raw_data` | Raw API JSON snapshot per rental listing. |

### User data

| Table | Purpose |
|---|---|
| `user_favorites` | `(user_id, listing_id)` — user-defined favorites (buy + rental). |
| `user_hidden` | `(user_id, listing_id)` — listings hidden by a user. |

`user_id` references `neon_auth.users.id` (no cross-schema FK — enforced in application code).

## Key Behaviours

- **`is_deleted` guard** — once a listing is marked deleted, it is never overwritten by new scrape data, even if the listing reappears in the feed.
- **City-scoped deactivation** — `deactivate_missing` only marks rows inactive within the same city, so parallel city jobs cannot interfere with each other.
- **Typology mapping** — Imovirtual returns English word counts (`THREE`). Converted via `word2number` → subtract 1 → Portuguese label (`T2`). Falls back to title regex (`T2`, `T 2`) if `roomsNumber` is absent.
- **Lifetime rent detection** — searches both `shortDescription` and `fullDescription` for keywords like `vitalícia`, `vitalicio`.
- **URL sanitisation** — `/hpr/` segments stripped from all URLs before any DB operation.

## Disclaimer

For personal and educational use only. Respect rate limits.
