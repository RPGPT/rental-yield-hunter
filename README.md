# Rental Yield Hunter

Daily scraper for Porto apartment listings on imovirtual.com. Stores structured data in PostgreSQL, tracks price changes, and flags properties with existing tenants.

## Stack

- Python 3.12
- PostgreSQL (Neon free tier / local Docker)
- curl_cffi (TLS-fingerprinted HTTP)
- SQLAlchemy + Alembic
- GitHub Actions (daily cron)

## Structure

```
rental-yield-hunter/
├── config.py                   # global settings (max price, keywords)
├── main.py                     # CLI entry point
├── seed.py                     # seed test data
├── scraper/
│   ├── base.py                 # Scraper ABC
│   ├── utils.py                # shared helpers (tenant detection)
│   └── imovirtual/
│       ├── __init__.py         # ImovirtualScraper
│       ├── constants.py        # source-specific maps
│       ├── fetcher.py          # HTTP + pagination
│       └── parser.py           # JSON → normalised dicts
├── db/
│   ├── client.py               # engine + session
│   ├── models.py               # Listing, PriceHistory, RawData
│   └── repository.py           # batch upsert
├── migrations/
├── tests/
│   ├── conftest.py             # testcontainers fixtures
│   ├── test_parser.py
│   ├── test_fetcher.py
│   ├── test_repository.py
│   ├── test_utils.py
│   └── test_integration.py
└── .github/workflows/
    └── scrape.yml              # daily CI/CD
```

## Setup

```bash
git clone https://github.com/RPGPT/rental-yield-hunter.git
cd rental-yield-hunter
cp .env.example .env            # edit DATABASE_URL
pip install -r requirements.txt
alembic upgrade head
```

## Usage

```bash
python main.py                      # scrape imovirtual
python main.py --source imovirtual  # explicit
```

## Tests

Requires Docker (testcontainers spins up a temporary Postgres).

```bash
pytest
```

## GitHub Actions

Runs daily at 08:00 UTC. Set `DATABASE_URL` as a repository secret.

Can also be triggered manually via `workflow_dispatch`.

## Schema

| Table | Purpose                                            |
|---|----------------------------------------------------|
| `listings` | All properties ≤405k (24 columns, PK = listing ID) |
| `listing_price_history` | Price change log                                   |
| `raw_data` | Raw API JSON per listing                           |

## Disclaimer

For personal and educational use only. Respect rate limits.
