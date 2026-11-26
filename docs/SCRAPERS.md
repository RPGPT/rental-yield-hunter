# Scrapers

Two sources, each with buy + rent variants. All HTTP goes through `curl_cffi.requests.Session(impersonate="chrome")`
with `time.sleep(REQUEST_DELAY)` between requests.

| | Imovirtual | ERA |
|---|---|---|
| Package | `yieldhunter/sources/imovirtual/` | `yieldhunter/sources/era/` |
| `source` value | `imovirtual` | `era` |
| Listing `id` | Imovirtual ad id (`item["id"]`, or regex `ID<x>` from URL) | `era-<Reference>` |
| Transport | Next.js `_next/data/<buildId>/<path>.json` | POST JSON API with CSRF token |
| Sorting | `by=PRICE&direction=ASC`, stops when page min price > ceiling | `order: 3` + same ceiling check |
| Session reuse | `fetch_with_context` passes `(session, build_id)` to `enrich` | `fetch_with_context` passes `(session, token)` to `enrich` |
| Buy enrich | Detail JSON for weekly-rotating subset + known/flagged rented | Detail API for **every** buy listing |
| Rent enrich | none | none |

## Imovirtual (`yieldhunter/sources/imovirtual/`)

### Fetch (`client.fetch_with_context`)
1. GET HTML search page (`BUY_CITY_PATHS[city][0]`) and read `buildId` from `<script id="__NEXT_DATA__">`.
2. Loop `GET {BASE}_next/data/{buildId}/{api_path}?page=N&by=PRICE&direction=ASC` with `x-nextjs-data: 1` ->
   `pageProps.data.searchAds` (`{items, pagination}`).
3. Stop when `min_price(items) > max_price`, `page >= totalPages`, or `not items`. If `buildId` is missing or any page
   returns non-200 / missing `searchAds`, `complete` is marked `False`.

See [FILTERS.md](../yieldhunter/sources/imovirtual/FILTERS.md) for URL filter details.

### Parse (`parser.parse_listing`)
- Price from `totalPrice.value`, filtered to `[MIN, MAX]`.
- URL: `[lang]` → `pt`, `/ad/` → `/anuncio/`, `/hpr/` stripped.
- Location: `reverseGeocoding.locations` (`parish` → neighborhood, `council` → city), falling back to `address.city` /
  `address.province`.
- City filter: for `PARISH_CITIES`, parish must equal target and `city = target`; otherwise council must equal target.
- Typology: `rooms_word_to_typology(roomsNumber)` (`word2number(n) - 1` → `T{n-1}`), falling back to `typology_from_title`.

### Enrich (`client.fetch_details`, buy only)
Candidates are listings that are:
- already flagged `is_rented` by the parser, **or**
- in `known_rented_ids` (previously rented in DB for this city+source; forced `is_rented=True` first), **or**
- in today's scan bucket: `sha256(id)[:4] % 7 == today.toordinal() % 7`.

Reuses `(session, build_id)` from `fetch_with_context` when run via `ImovirtualBuyScraper.run()`, fetches
`_next/data/{buildId}/{path}.json`, updates `description`, `is_rented`, and `lifetime_rent`, and stores
`fullDescription` inside `_raw_json` so contract extraction needs no extra HTTP calls.

## ERA (`yieldhunter/sources/era/`)

### Fetch (`client.fetch_with_context`)
1. GET HTML search page (`CITY_CONFIG[city][1]`) and regex out `__RequestVerificationToken`, `data-moduleid`, and `data-tabid`.
2. POST `API/ServicesModule/Property/Search` with `RequestVerificationToken`, `ModuleId`, `TabId` headers and body
   `{businessTypeId:[1|2], propertiesTypeId:[1], locationId:[<dd-mm>], page, order:3}`.
3. Stops on empty `PropertyList`, min price > ceiling, or `page >= TotalPages`. Token failure or non-200 sets `complete=False`.

### Parse (`parser.parse_listing`)
- Price from `SellPrice.Value` / `RentPrice.Value` in PT format (`"255.000 €"`); non-numeric prices skipped.
- Skips `IsOnline == False` and `BusinessStatus.Id != 1` (reserved/sold).
- `SEARCH_SCOPED_CITIES` (Paços de Ferreira, Paredes, Penafiel, Ermesinde, Alfena): trusts the municipality-scoped search
  and sets `city = target` (checking parish presence for `PARISH_CITIES`).
- Typology: `rooms_int_to_typology(Rooms)` (`T{Rooms}`, no −1), falling back to `typology_from_title`.

### Enrich (`client.fetch_details`, buy only)
Reuses `(session, token)` from `fetch_with_context` and GETs `PropertyDetailByReference?reference=…` for every buy
listing to populate `description`, `is_rented`, and `lifetime_rent`.

## Adding a city

1. `yieldhunter/config.py`: add to `SUPPORTED_CITIES` (and `PARISH_CITIES` if it is a freguesia).
2. `yieldhunter/sources/imovirtual/constants.py`: add to `BUY_CITY_PATHS` (`RENTAL_CITY_PATHS` is derived automatically!).
3. `yieldhunter/sources/era/constants.py`: add to `CITY_CONFIG` (and `SEARCH_SCOPED_CITIES` if needed).
4. `.github/workflows/scrape.yml`: add to `city` dispatch options and both matrix JSON lists.
5. `yieldhunter/analysis/normalization.py`: add parish aliases + a data migration for existing rows (see 0026).
6. Update city list assertions in `tests/test_scrapers.py`.

## Adding a source

Create `yieldhunter/sources/<source>/{__init__,constants,client,parser}.py` subclassing `Scraper` (set
`self.last_fetch_complete = complete`), prefix listing IDs to avoid PK collisions, register in
`yieldhunter/sources/registry.py`, and add to `.github/workflows/scrape.yml`.
