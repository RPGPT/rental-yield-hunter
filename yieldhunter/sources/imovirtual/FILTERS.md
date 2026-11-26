# Imovirtual.com — Filter Reference

All available filters for scraping imovirtual.com. Filters are applied via **URL path segments** (not query strings).

> ⚠️ Query string parameters (e.g. `?priceMin=100000`) are handled **client-side only** and are ignored by the server — the `__NEXT_DATA__` JSON always returns the same results regardless of query params.

---

## URL Pattern

```
https://www.imovirtual.com/{transaction}/{estate}/{district}/{concelho}/
```

All segments are optional (left to right). Deeper segments narrow the search.

---

## Transaction (required)

| Value | Description | URL Segment |
|---|---|---|
| Buy | Properties for sale | `comprar` |
| Rent | Properties for rent | `arrendar` |

**Examples:**
```
/comprar/apartamento/porto/     → buy apartments in Porto district
/arrendar/apartamento/porto/    → rent apartments in Porto district
```

---

## Estate / Property Type

| Value | Description | URL Segment | Internal Value |
|---|---|---|---|
| Apartment | Flats | `apartamento` | `FLAT` |
| House | Villas/houses | `moradia` | `HOUSE` |
| Land | Plots | `terreno` | `TERRAIN` |
| Garage | Parking spaces | `garagem` | `GARAGE` |
| Warehouse | Storage/industrial | `armazem` | `WAREHOUSE` |
| All types | No filter | _(omit segment)_ | — |

**Examples:**
```
/comprar/apartamento/porto/    → apartments only
/comprar/moradia/porto/        → houses only
/comprar/porto/                → all property types (default: apartments in response)
```

---

## Location Hierarchy

```
District → Concelho (Council/Municipality) → Freguesia (Parish)
```

| Level | URL Segment | Example | Works? |
|---|---|---|---|
| District | `/{district}/` | `/porto/` | ✅ |
| Concelho | `/{district}/{concelho}/` | `/porto/matosinhos/` | ✅ |
| Freguesia | `/{district}/{concelho}/{freguesia}/` | `/porto/porto/paranhos/` | ❌ (returns all) |

### Porto District — Concelhos (Municipalities)

| Concelho | URL Segment | Approx. Listings (sale) |
|---|---|---|
| Porto (city) | `porto/porto/` | ⚠️ broken — returns all |
| Matosinhos | `porto/matosinhos/` | ~2,759 |
| Vila Nova de Gaia | `porto/vila-nova-de-gaia/` | ~6,639 |
| Maia | `porto/maia/` | varies |
| Gondomar | `porto/gondomar/` | varies |
| Valongo | `porto/valongo/` | varies |
| Paredes | `porto/paredes/` | varies |
| Penafiel | `porto/penafiel/` | varies |
| Marco de Canaveses | `porto/marco-de-canaveses/` | varies |
| Amarante | `porto/amarante/` | varies |
| Baião | `porto/baiao/` | varies |
| Felgueiras | `porto/felgueiras/` | varies |
| Lousada | `porto/lousada/` | varies |
| Paços de Ferreira | `porto/pacos-de-ferreira/` | varies |
| Santo Tirso | `porto/santo-tirso/` | varies |
| Trofa | `porto/trofa/` | varies |
| Vila do Conde | `porto/vila-do-conde/` | varies |
| Póvoa de Varzim | `porto/povoa-de-varzim/` | varies |

> **Note:** `/porto/` alone (district level) returns only Porto city (~9,143 results). To get all of Porto district, omit the concelho or use individual concelho URLs.

---

## Sorting

Sorting is applied via the `by` and `direction` query params. These **are handled server-side** in the JSON response order.

| Sort | `by` | `direction` |
|---|---|---|
| Newest first | `LATEST` | `DESC` |
| Price ascending | `PRICE` | `ASC` |
| Price descending | `PRICE` | `DESC` |
| Area ascending | `AREA` | `ASC` |
| Area descending | `AREA` | `DESC` |

**Example:**
```
/comprar/apartamento/porto/?by=PRICE&direction=ASC
```

---

## Pagination

| Parameter | Description | Default |
|---|---|---|
| `page` | Page number (1-based) | `1` |
| `limit` | Items per page | `36` |

**Example:**
```
/comprar/apartamento/porto/?page=2
```

---

## Listing Tags (available in JSON response)

Tags are present in each listing's `tags` array. Not filterable via URL, but useful for post-processing.

| Tag Value | Description |
|---|---|
| `PARKING_SPOT` | Has parking |
| `STORAGE_ROOM` | Has storage |
| `GARDEN` | Has garden |
| `TERRACE` | Has terrace |
| `BALCONY` | Has balcony |
| `POOL` | Has pool |
| `AIR_CONDITIONING` | Has A/C |
| `SEPARATE_KITCHEN` | Separate kitchen |
| `SECURE_BUILDING` | Gated/secure building |
| `TOP_FLOOR` | Top floor |
| `GROUND_FLOOR` | Ground floor |

---

## Investment State

Available in the `investmentState` field of each listing. Most listings have `null`.

| Value | Description |
|---|---|
| `null` | Standard listing |
| `IN_BUILDING` | Under construction |
| `READY_TO_USE` | Move-in ready |
| `TO_RENOVATION` | Needs renovation |
| `TO_COMPLETION` | Needs finishing |

---

## Tenant Detection (Keyword-Based)

There is **no server-side filter** for "sold with tenants" or "rented". Detection is done by searching the listing `title` and `shortDescription` for Portuguese keywords:

| Keyword | Meaning |
|---|---|
| `arrendado` | Rented/leased |
| `inquilino` | Tenant |
| `rentabilidade` | Yield/profitability |
| `arrendamento` | Lease agreement |
| `renda` | Rent income |
| `rented` | Rented (English) |
| `yield` | Yield (English) |
| `tenant` | Tenant (English) |

---

## JSON Response Fields (per listing)

Each listing in `__NEXT_DATA__.props.pageProps.data.searchAds.items[]` contains:

| Field | Type | Description |
|---|---|---|
| `id` | int | Unique listing ID |
| `title` | string | Listing title |
| `slug` | string | URL slug |
| `estate` | string | `FLAT`, `HOUSE`, etc. |
| `transaction` | string | `SELL`, `RENT` |
| `totalPrice.value` | int | Sale price (EUR) |
| `totalPrice.currency` | string | `EUR` |
| `rentPrice.value` | int | Monthly rent (if rental) |
| `pricePerSquareMeter.value` | int | €/m² |
| `areaInSquareMeters` | int | Total area (m²) |
| `terrainAreaInSquareMeters` | int | Terrain area (if land) |
| `roomsNumber` | string | `ONE`, `TWO`, `THREE`, `FOUR`, `FIVE_OR_MORE` |
| `floorNumber` | int | Floor number |
| `location.address.street.name` | string | Street name |
| `location.address.city.name` | string | City/concelho |
| `location.address.province.name` | string | District |
| `shortDescription` | string | Listing description excerpt |
| `dateCreated` | string | Publication date |
| `createdAtFirst` | string | First publication date (ISO 8601) |
| `investmentState` | string | See above |
| `tags` | array | See tags table above |
| `images` | array | Image URLs |
| `href` | string | Relative URL to listing detail |
| `agency.name` | string | Real estate agency name |
| `isPrivateOwner` | bool | Direct from owner |
| `isPromoted` | bool | Promoted listing |
| `isExclusiveOffer` | bool | Exclusive |

---

## Useful URL Examples

```bash
# Buy apartments in Porto district
https://www.imovirtual.com/comprar/apartamento/porto/

# Buy houses in Matosinhos
https://www.imovirtual.com/comprar/moradia/porto/matosinhos/

# Rent apartments in Porto district
https://www.imovirtual.com/arrendar/apartamento/porto/

# Buy apartments in Vila Nova de Gaia, sorted by price
https://www.imovirtual.com/comprar/apartamento/porto/vila-nova-de-gaia/?by=PRICE&direction=ASC

# Buy land in Porto district
https://www.imovirtual.com/comprar/terreno/porto/

# Page 3 of apartments for sale
https://www.imovirtual.com/comprar/apartamento/porto/?page=3
```

