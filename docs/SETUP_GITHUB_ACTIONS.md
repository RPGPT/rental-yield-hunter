# GitHub Actions Setup Guide

## Step 1: Create a Free Postgres Database (Neon)

1. Go to [neon.tech](https://neon.tech) and sign up with your GitHub account
2. Click **Create Project**
   - Name: `rental-yield-hunter`
   - Postgres version: `16`
   - Region: pick the closest to you (e.g. `EU West - Frankfurt`)
3. Once created, copy the **connection string** from the dashboard. It looks like:

```
postgresql://neondb_owner:abc123xyz@ep-cool-name-12345.eu-west-1.aws.neon.tech/neondb?sslmode=require
```

> **Why Neon?** Free tier gets 0.5 GB storage, always-on compute, no credit card needed. Other options: [Supabase](https://supabase.com), [Railway](https://railway.app), [ElephantSQL](https://www.elephantsql.com).

## Step 2: Add the Database URL to GitHub Secrets

1. Go to your repo: [github.com/RPGPT/rental-yield-hunter](https://github.com/RPGPT/rental-yield-hunter)
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `DATABASE_URL`
5. Value: paste the connection string from Step 1
6. Click **Add secret**

## Step 3: Run the Workflow

The pipelines are configured in `.github/workflows/`:

| Workflow | File | Triggers | What it does |
|---|---|---|---|
| **Test** | `test.yml` | PRs, manual | Throwaway Postgres, migrations, pytest |
| **Scrape** | `scrape.yml` | Daily 08:00 UTC, manual | Neon DB, migrations, scrape imovirtual |

### Trigger scrape manually (first time)

1. Go to **Actions** tab in your repo
2. Click **Scrape** in the left sidebar
3. Click **Run workflow** → **Run workflow**

### Automatic schedule

The workflow runs automatically every day at **08:00 UTC** via cron.

## Step 4: Verify

After the first run:

1. Check the **Actions** tab — both jobs should be green ✓
2. Go to your Neon dashboard → **SQL Editor**
3. Run:

```sql
SELECT count(*) FROM listings;
SELECT * FROM listings ORDER BY price ASC LIMIT 5;
```

You should see scraped Porto apartment listings.

## Troubleshooting

| Problem | Fix |
|---|---|
| `scrape` job fails with "DATABASE_URL" error | Secret not set — repeat Step 2 |
| `test` job fails | Check pytest output in the Actions log |
| 0 listings after scrape | imovirtual may have changed their API — check the scrape logs |
| Neon DB sleeping | Free tier auto-suspends after 5 min idle — first connection takes ~1s to wake |

