# Rental Yield Hunter

Daily scraper and investment-analysis pipeline for Porto-area apartment listings across **imovirtual.com**, **era.pt**,
and **casa.sapo.pt**. Tracks buy and rental listings, preserves original asking prices and cumulative price cuts, flags
tenanted properties, computes lease-expiry reversion upside, deduplicates multi-agency listings to surface price spreads,
estimates non-linear market rent and gross yield, and dispatches saved-search deal alerts.

> Working on this repo with an AI agent? Start with [AGENTS.md](AGENTS.md). Deeper docs live in [docs/](docs/).

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 (`yieldhunter` package) |
| HTTP | `curl_cffi` (Chrome TLS-fingerprint impersonation + polite backoff) |
| ORM / Migrations | SQLAlchemy + Alembic (`0001` → `0030`) |
| Parsing helpers | `word2number` (typology/floors), `dateparser` (contract expiry) |
| Database | PostgreSQL: Neon (prod) / testcontainers (tests) |
| CI / CD | GitHub Actions: `test.yml` (PRs), `scrape.yml` (daily 04:00 UTC), `migrate.yml` (manual) |
| Alerts | Telegram Bot API, Resend Email API, or JSON Webhook (optional secrets) |
| Frontend | Angular 21 + Neon Auth (separate repo, reads the same DB) |

## Coverage

- **Sources:** Imovirtual (`imovirtual`), ERA (`era`), Casa Sapo (`casasapo`)
- **Cities:** Porto · Matosinhos · Vila Nova de Gaia · Maia · Paços de Ferreira · Penafiel · Paredes · Ermesinde · Alfena
- **Price bands:** buy €50k–€405k · rent €300–€4,000/month (`yieldhunter/config.py`)

## Daily Pipeline

```
scrape buy (3 sources × 9 cities) ─▶ scrape rent (3 sources × 9 cities) ─┬─▶ extract contracts + lease upside
                                                                         ├─▶ refresh size-curved rent estimates
                                                                         └─▶ cluster multi-agency duplicates
                                                                                       │
                                                                                       ▼
                                                                           dispatch saved-search alerts ─▶ summary
```

1. **Scrape (`yieldhunter/sources/`).** Sorted cheapest-first, stopping at the price ceiling; incomplete runs skip deactivation.
2. **Price-drop & motivated-seller signals (`yieldhunter/db/repository/listings.py`).** Preserves `initial_price`, stores
   `previous_price` on every history entry, and maintains `price_drop_amount`, `price_drop_pct`, and `price_change_count`.
3. **Contract extraction & lease-expiry upside (`yieldhunter/db/repository/contracts.py`).** Extracts `current_rent` and
   `contract_expiry_date` from stored descriptions and computes `current_yield`, `reversion_yield`, `rent_upside_pct`, and
   `months_to_expiry`.
4. **Size-curved rental estimates (`yieldhunter/db/repository/estimates.py`).** Weighted-median comparables adjusted along
   `area^0.30` over active + 60-day recently-rented listings.
5. **Cross-source deduplication & arbitrage (`yieldhunter/analysis/clustering.py`).** Clusters duplicate ads across
   Imovirtual, ERA, and Casa Sapo into `listing_clusters` (`price_spread`, `is_cheapest`, `sources`).
6. **Saved-search deal alerts (`yieldhunter/pipeline/alerts.py`).** Matches new deals and price drops against
   `saved_searches.filters` and delivers digests via Telegram, Resend, or Webhook (`alert_notifications` dedup).

## Usage

```bash
python3 -m yieldhunter                                    # Imovirtual, buy, all cities
python3 -m yieldhunter --source casasapo --city Porto     # Casa Sapo buy in Porto
python3 -m yieldhunter --source era --type rent           # ERA rentals
python3 -m yieldhunter --type estimates [--city Maia]     # recompute rental estimates + lease upside
python3 -m yieldhunter --type contracts [--city Maia]     # extract rent/expiry + lease upside
python3 -m yieldhunter --type clusters  [--city Porto]    # deduplicate multi-agency ads & spreads
python3 -m yieldhunter --type alerts                      # evaluate saved_searches & send alerts
python3 -m yieldhunter --type summarize --stats-dir .     # render CI Markdown run summary
```

## Tests & Linting

```bash
python3 -m pytest tests/ -v
python3 -m ruff check --fix . && python3 -m ruff format .
```

## Schema

| Table | Purpose |
|---|---|
| `listings` | Buy listings (`initial_price`, `price_drop_amount`, `price_drop_pct`, `price_change_count`, `is_rented`, `lifetime_rent`) |
| `listing_price_history` / `raw_data` | Buy price changes (`previous_price`, `price`) and latest raw JSON |
| `rental_listings` | Rental listings (`rent_price_per_m2` + price-drop signals) |
| `rental_listing_price_history` / `rental_raw_data` | Rental price changes and latest raw JSON |
| `rental_estimates` | Size-curved estimated rent, €/m², sample count, confidence, match level, gross yield |
| `rent_contract_details` | Extracted rent/expiry + `current_yield`, `reversion_yield`, `rent_upside_pct`, `months_to_expiry` |
| `listing_clusters` | Physical-apartment `cluster_id`, `cluster_size`, `price_spread`, `is_cheapest`, `sources` |
| `saved_searches` / `alert_notifications` | User saved searches (`filters` JSONB) and sent-alert deduplication log |
| `user_favorites`, `user_hidden`, `audit_log`, `listing_snapshots` | Frontend user & archival tables |

Full column reference: [docs/DATA_MODEL.md](docs/DATA_MODEL.md).
