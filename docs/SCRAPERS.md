# Scrapers

Two sources, each with buy + rent variants. All HTTP goes through `curl_cffi.requests.Session(impersonate="chrome")`
(TLS fingerprint spoofing), with `time.sleep(REQUEST_DELAY)` between requests.

| | Imovirtual | ERA |
|---|---|---|
| Package | `scraper/imovirtual/` | `scraper/era/` |
| `source` value | `imovirtual` | `era` |
| Listing `id` | Imovirtual ad id (`item["id"]`, or regex `ID<x>` from the URL) | `era-<Reference>` |
| Transport | Next.js `_next/data/<buildId>/<path>.json` | POST JSON API with CSRF token |
| Sorting | `by=PRICE&direction=ASC`, stops when page min price > ceiling | `order: 3` + same ceiling check |
| Buy enrich | Detail JSON for a weekly-rotating subset (see below) | Detail API for **every** buy listing |
| Rent enrich | none | none |

## Imovirtual

### Fetch (`fetcher.fetch`)
1. GET the HTML search page (`BUY_CITY_PATHS[city][0]`) and read `buildId` from `<script id="__NEXT_DATA__">`.
2. Loop `GET {BASE}_next/data/{buildId}/{api_path}?page=N&by=PRICE&direction=ASC` with header `x-nextjs-data: 1`, and
   read `pageProps.data.searchAds` → `{items, pagination}`.
3. Stop when there's no data, the cheapest item on the page is above `MAX_PRICE`, or `page >= totalPages`.

Query-string filters (`priceMin` etc.) are ignored server-side, which is why we sort by price and cut off.
See [FILTERS.md](../scraper/imovirtual/FILTERS.md).

### Parse (`parser.parse_listing`)
- Price from `totalPrice.value`, filtered to `[MIN, MAX]`.
- URL: `[lang]` → `pt`, `/ad/` → `/anuncio/`, `/hpr/` stripped.
- Location: `reverseGeocoding.locations` (`parish` → neighborhood, `council` → city), falling back to `address.city` /
  `address.province`.
- City filter: for `PARISH_CITIES`, the parish must equal the target and `city` is set to the parish. Otherwise the council must
  equal the target.
- Typology: `rooms_to_typology(roomsNumber)` = word2number(n) − 1 → `T{n-1}`, or a title regex `T\s*(\d+)`.
- `has_garage`: `PARKING_SPOT` tag or "garage" in features. `property_type` comes from `ESTATE_MAP` (`FLAT` → `apartment` …).
- `is_rented` is checked on title + `shortDescription`. `lifetime_rent=False` until enrich.

### Enrich (`fetcher.fetch_details`, buy only)
Candidates are listings that are:
- already flagged `is_rented` by the parser, **or**
- in `known_rented_ids` (previously rented in DB for this city+source; these are forced to `is_rented=True` first), **or**
- in today's scan bucket: `sha256(id)[:4] % 7 == today.toordinal() % 7`.

For each candidate it GETs `_next/data/{buildId}/{listing path}.json` → `pageProps.ad.{description, fullDescription}`, then
recomputes `is_rented` (title + both descriptions) and `lifetime_rent`, and stores `fullDescription` into `_raw_json`.
If the detail fetch fails, the existing flag is kept (OR'd with a keyword check).

## ERA

### Fetch (`era/fetcher.fetch`)
1. GET the HTML search page (`CITY_CONFIG[city][1]`) and regex out `__RequestVerificationToken`, `data-moduleid` and
   `data-tabid` (fallbacks: `MODULE_ID=410`, `TAB_ID=36`).
2. POST `API/ServicesModule/Property/Search` with headers `RequestVerificationToken`, `ModuleId`, `TabId`, `Referer`, and
   body `{businessTypeId:[1 buy | 2 rent], propertiesTypeId:[1], locationId:[<dd-mm>], page, order:3}`.
3. Response: `{TotalPages, PropertyList:[…]}`. Stops on an empty list, min price > ceiling, or the last page.

### Parse (`era/parser.parse_listing`)
- Price from `SellPrice.Value` / `RentPrice.Value` in PT format (`"255.000 €"`). "Sob consulta" → skip.
- Skips `IsOnline == False` and `BusinessStatus.Id != 1` (reserved/sold).
- `Localization` `"Parish, Municipality"` → split on the last comma.
- `SEARCH_SCOPED_CITIES` (Paços de Ferreira, Paredes, Penafiel, Ermesinde, Alfena): ERA's suffix is often the *district*,
  so we trust the municipality-scoped search and force `city = target`. For parish cities, the parish must appear in
  `Localization`. Other cities: the suffix must equal the target.
- `price_per_m2 = price / ListingArea`. For rent this is also `rent_price_per_m2`.
- Typology from `Rooms` (`T{Rooms}`, **no** −1), falling back to the title regex. `has_garage = Parking > 0`.

### Enrich (`era/fetcher.fetch_details`, buy only)
For every listing: GET `API/ServicesModule/Property/PropertyDetailByReference?reference=…` with the hardcoded
`DETAIL_MODULE_ID=641` / `DETAIL_TAB_ID=256`, take `Description`, and set `description`, `is_rented` and `lifetime_rent`.

### City config (`era/constants.CITY_CONFIG`)
`city → (location_id "13-NN", buy search path)`. Ermesinde and Alfena both use Valongo (`13-15`) and are filtered by parish.

## Adding a city

1. `config.SUPPORTED_CITIES` (and `PARISH_CITIES` if it's a freguesia rather than a concelho).
2. `scraper/imovirtual/constants.py`: add to both `BUY_CITY_PATHS` and `RENTAL_CITY_PATHS` (search path + `pt/resultados/... .json`).
3. `scraper/era/constants.py`: add to `CITY_CONFIG`, and to `SEARCH_SCOPED_CITIES` if ERA's `Localization` suffix is unreliable.
4. `.github/workflows/scrape.yml`: add it to the `city` dispatch options **and** both matrix JSON lists.
5. Add neighborhood aliases in `normalization.py` plus a data migration for existing rows (see 0026).
6. Tests: `tests/test_scrapers.py` / `test_parser.py` usually assert the city lists.

## Adding a source

Create `scraper/<source>/{__init__,constants,fetcher,parser}.py` that mirrors ERA. Subclass `Scraper`, emit the normalised dict
(see [ARCHITECTURE.md](ARCHITECTURE.md#normalised-listing-dict-parser-output--db-row-input)), and prefix IDs so they
can't collide. Register it in `main.SCRAPERS` and add it to the workflow `source` options/matrix.
