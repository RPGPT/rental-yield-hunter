# Scrapers

Three sources, each with buy + rent variants. All HTTP goes through `curl_cffi.requests.Session(impersonate="chrome")`.

| | Imovirtual | ERA | Casa Sapo |
|---|---|---|---|
| Package | `yieldhunter/sources/imovirtual/` | `yieldhunter/sources/era/` | `yieldhunter/sources/casasapo/` |
| `source` value | `imovirtual` | `era` | `casasapo` |
| Listing `id` | numeric ad id | `era-<Reference>` | `casasapo-<UUID>` |
| Transport | Next.js `_next/data/<buildId>/<path>.json` | POST JSON API + CSRF token | Server-rendered HTML + embedded `schema.org` JSON-LD |
| Sorting | `by=PRICE&direction=ASC` | `order: 3` (price asc) | `/mais-baratos/…?sa=13&pn=N` |
| Buy enrich | Weekly-rotating detail JSON + rented IDs | Detail API for every buy listing | **None needed** (full `.property-description` is on search cards) |
| Rent enrich | none | none | none |

## Imovirtual (`yieldhunter/sources/imovirtual/`)
- Reads `buildId` from `__NEXT_DATA__`, paginates `_next/data/{buildId}/{api_path}?page=N&by=PRICE&direction=ASC`, and
  reuses `(session, build_id)` in `fetch_details` for weekly bucket candidates + known/flagged rented listings.
- `roomsNumber` includes the living room (`"THREE"` → `T2`). See [FILTERS.md](../yieldhunter/sources/imovirtual/FILTERS.md).

## ERA (`yieldhunter/sources/era/`)
- Extracts `__RequestVerificationToken`, `data-moduleid`, and `data-tabid` from search HTML, POSTs `Property/Search`,
  skips reserved listings (`BusinessStatus.Id != 1`), and enriches every buy listing via `PropertyDetailByReference`.

## Casa Sapo (`yieldhunter/sources/casasapo/`)
- Fetches `/{comprar|arrendar}-apartamentos/mais-baratos/{slug}/?sa=13[&pn=N]` with a polite `3.0s` delay and automatic
  backoff (`12s`, `25s`) on HTTP `429`.
- Parses each `<div id="property_<UUID>" class="property">` card, combining embedded `<script type="application/ld+json">`
  (`RealEstateListing` price, `floorSize`, geo/address) with `.property-location`, `.property-features`, and the
  untruncated `.property-description` (setting `is_rented`, `lifetime_rent`, and `_raw_json['fullDescription']` in one pass).

## Adding a city
1. `yieldhunter/config.py`: add to `SUPPORTED_CITIES` (and `PARISH_CITIES` if it is a parish).
2. `yieldhunter/sources/imovirtual/constants.py`: add to `BUY_CITY_PATHS`.
3. `yieldhunter/sources/era/constants.py`: add to `CITY_CONFIG` (and `SEARCH_SCOPED_CITIES` if needed).
4. `yieldhunter/sources/casasapo/constants.py`: add to `CITY_SLUGS`.
5. `.github/workflows/scrape.yml`: add to `city` dispatch options and matrix JSON lists.
6. `yieldhunter/analysis/normalization.py`: add parish aliases + data migration for existing rows.

## Adding a source
Create `yieldhunter/sources/<source>/{__init__,constants,client,parser}.py` subclassing `Scraper` (setting
`self.last_fetch_complete = complete`), prefix listing IDs, register in `yieldhunter/sources/registry.py`, and add to
`.github/workflows/scrape.yml`.
