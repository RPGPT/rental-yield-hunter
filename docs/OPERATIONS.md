# Operations

## Local setup

```bash
uv venv -p 3.12 .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # DATABASE_URL=postgresql://user:password@host:5432/db
python -m alembic upgrade head
```

## Running

```bash
python -m yieldhunter                                      # imovirtual, buy, all cities
python -m yieldhunter --source casasapo --city Maia        # Casa Sapo buy in Maia
python -m yieldhunter --source era --city Maia --type rent # ERA rentals
python -m yieldhunter --type estimates [--city Porto]      # refresh estimates + lease upside
python -m yieldhunter --type contracts [--city Porto]      # extract contracts + lease upside
python -m yieldhunter --type clusters  [--city Porto]      # cluster multi-agency duplicates
python -m yieldhunter --type alerts                        # evaluate saved_searches & send alerts
```

## Optional Alert Secrets (GitHub Actions / `.env`)

Configure one or more channels for `--type alerts`:
- **Telegram:** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (or per-search `filters.telegram_chat_id`).
- **Email (Resend):** `RESEND_API_KEY`, `ALERT_FROM_EMAIL` (default `alerts@yieldhunter.pt`), and `ALERT_TO_EMAIL`
  (automatically resolves per-user email from `neon_auth.user` in Neon when present, or `filters.email`).
- **Webhook:** `ALERT_WEBHOOK_URL` (or per-search `filters.webhook_url`).

If no delivery channel is configured, `--type alerts` logs matches and writes `stats-alerts.json` without advancing
`last_checked_at`, so pending matches still fire once a channel is configured.

## Tests & Lint

```bash
python -m pytest tests/ -v
python -m ruff check --fix . && python -m ruff format .
```

- `tests/test_casasapo.py` tests Casa Sapo parsing against real captured HTML (`tests/fixtures/http/casasapo_alfena.html`)
  plus 429 retry/backoff handling.
- `tests/test_clusters.py` and `tests/test_alerts.py` cover physical deduplication and saved-search alert lifecycles.
- `tests/flows/test_main_flows.py` runs real Alembic `0001` → `0030` migrations and verifies golden parity, price-drop
  signals, lease-upside fields, clustering, alerts, and incomplete-scrape safety.
