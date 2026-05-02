# 🏠 Porto Property Scraper (imovirtual.com)

Python bot for daily scraping of property listings on imovirtual.com (Porto district), storing data in PostgreSQL, and identifying properties with existing tenants.

Extracts structured JSON directly from imovirtual's `__NEXT_DATA__` — no API keys, no browser automation, no CAPTCHA solving needed.

## 🚀 Goals

* Daily scraping of properties for sale in Porto
* Store data in PostgreSQL (Supabase free tier or local)
* Detect listings with tenants (keywords: arrendado, inquilino, rentabilidade)
* Keep history (delta via upsert)
* Run locally + CI (GitHub Actions cron)

## 🧠 Stack

* Python 3.9+
* PostgreSQL (Supabase or local)
* curl_cffi (HTTP client with TLS fingerprinting)
* SQLAlchemy + Alembic (models + migrations)
* GitHub Actions (daily cron at 07:00 UTC)

## 📁 Structure

```
rental-yield-hunter/
├── scraper/
│   ├── utils.py               # shared helpers (tenant keyword detection)
│   ├── imovirtual/
│   │   ├── fetcher.py         # fetch listings from imovirtual.com
│   │   └── parser.py          # parse __NEXT_DATA__ JSON
│   └── idealista/
│       ├── fetcher.py         # TODO: fetch from Idealista
│       └── parser.py          # TODO: parse Idealista data
├── db/
│   ├── models.py              # SQLAlchemy models
│   ├── client.py              # engine + session
│   └── repository.py          # listing upsert
├── migrations/                # Alembic migrations
├── .github/workflows/
│   └── scrape.yml             # GitHub Actions cron
├── alembic.ini
├── main.py                    # CLI entry point (--source imovirtual|idealista)
├── seed.py
├── test_e2e.py
├── requirements.txt
├── .env.example
└── README.md
```

## ⚙️ Local Setup

### 1. Clone

```bash
git clone <repo>
cd rental-yield-hunter
```

### 2. Create env file

```bash
cp .env.example .env
```

Edit `.env`:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start Postgres (docker, skip if already running locally)

```bash
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres
```

### 5. Apply migrations

```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

### 6. Run scraper

```bash
python main.py                      # default: imovirtual
python main.py --source imovirtual  # explicit
python main.py --source idealista   # stub (not implemented yet)
```

### 7. Run tests (optional)

```bash
python test_e2e.py
```

## 🤖 GitHub Actions

The workflow runs daily at 07:00 UTC. It can also be triggered manually via `workflow_dispatch`.

Set the `DATABASE_URL` secret in the repository.

## 📊 Data Fields

| Field | Source | Example |
|---|---|---|
| `id` | imovirtual listing ID | `18895371` |
| `title` | listing title | `Apartamento T1, Antas, no Porto` |
| `price` | sale price (EUR) | `215000` |
| `area` | area in m² | `46` |
| `location` | street, city, district | `Rua Tomás Ribeiro, Bonfim, Porto` |
| `url` | full listing URL | `https://www.imovirtual.com/pt/ad/...` |
| `has_tenants` | keyword detection | `true` / `false` |
| `last_seen` | last scrape timestamp | `2026-05-02 19:39:19` |

## 🧠 Future Improvements

* Scrape rental listings → compute real yield
* Telegram alerts
* Investment scoring
* Multi-source (casa.sapo.pt, supercasa.pt)
* Historical price tracking

## ⚠️ Disclaimer

* Use responsibly — add delays between requests
* This project is for personal and educational use only
