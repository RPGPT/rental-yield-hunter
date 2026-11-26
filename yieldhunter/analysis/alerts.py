"""Saved-search filter evaluation and deal-alert message formatting."""

from __future__ import annotations

from typing import Any


def _first_key(filters: dict, *keys: str) -> Any:
    for k in keys:
        if k in filters and filters[k] is not None and filters[k] != "":
            return filters[k]
    return None


def _as_set(val: Any) -> set[str] | None:
    if val is None:
        return None
    if isinstance(val, str):
        return {val.casefold()} if val.strip() else None
    if isinstance(val, (list, tuple, set)):
        items = {str(x).casefold() for x in val if x is not None and str(x).strip()}
        return items or None
    return None


def _normalize_fraction(val: Any) -> float | None:
    if val is None:
        return None
    f = float(val)
    # Accept both fraction (0.065) and percentage (6.5)
    return f / 100.0 if f > 1.0 else f


def matches_saved_search(listing: dict, filters: dict) -> bool:
    """Return ``True`` if *listing* satisfies every criterion in ``saved_searches.filters``."""
    if not filters:
        return True

    cities = _as_set(_first_key(filters, "cities", "city"))
    if cities and (listing.get("city") or "").casefold() not in cities:
        return False

    parishes = _as_set(_first_key(filters, "neighborhoods", "neighborhood"))
    if parishes and (listing.get("neighborhood") or "").casefold() not in parishes:
        return False

    sources = _as_set(_first_key(filters, "sources", "source"))
    if sources and (listing.get("source") or "").casefold() not in sources:
        return False

    typologies = _as_set(_first_key(filters, "typologies", "typology"))
    if typologies and (listing.get("typology") or "").casefold() not in typologies:
        return False

    price = listing.get("price")
    min_price = _first_key(filters, "min_price", "minPrice")
    if min_price is not None and (price is None or price < float(min_price)):
        return False
    max_price = _first_key(filters, "max_price", "maxPrice")
    if max_price is not None and (price is None or price > float(max_price)):
        return False

    area = listing.get("area")
    min_area = _first_key(filters, "min_area", "minArea")
    if min_area is not None and (area is None or area < float(min_area)):
        return False
    max_area = _first_key(filters, "max_area", "maxArea")
    if max_area is not None and (area is None or area > float(max_area)):
        return False

    min_yield = _normalize_fraction(_first_key(filters, "min_yield", "minYield"))
    if min_yield is not None:
        ry = listing.get("rental_yield")
        if ry is None or float(ry) < min_yield:
            return False

    is_rented_filter = _first_key(filters, "is_rented", "isRented")
    if isinstance(is_rented_filter, bool) and bool(listing.get("is_rented")) != is_rented_filter:
        return False

    excl_lifetime = _first_key(filters, "exclude_lifetime_rent", "excludeLifetimeRent")
    if excl_lifetime and listing.get("lifetime_rent"):
        return False

    has_garage = _first_key(filters, "has_garage", "hasGarage")
    if isinstance(has_garage, bool) and bool(listing.get("has_garage")) != has_garage:
        return False

    min_drop_pct = _normalize_fraction(_first_key(filters, "min_price_drop_pct", "minPriceDropPct"))
    if min_drop_pct is not None:
        dp = listing.get("price_drop_pct")
        if dp is None or float(dp) < min_drop_pct:
            return False

    only_cheapest = _first_key(filters, "only_cheapest_in_cluster", "onlyCheapestInCluster")
    if only_cheapest and listing.get("is_cheapest") is False:
        return False

    return True


def format_alert_digest_markdown(search_name: str, matches: list[dict]) -> str:
    lines = [f"🏠 *Rental Yield Hunter — {search_name}* ({len(matches)} new deal{'s' if len(matches) != 1 else ''})\n"]
    for m in matches[:15]:
        badge = "📉 Price Drop" if m["trigger_type"] == "price_drop" else "🆕 New"
        price_str = f"€{m['price']:,}"
        if m["trigger_type"] == "price_drop" and m.get("previous_price"):
            price_str += f" (was €{m['previous_price']:,})"
        yield_str = f"{float(m['rental_yield']) * 100:.1f}% yield" if m.get("rental_yield") is not None else "n/a yield"
        est_str = f"~€{m['estimated_rent']}/mo" if m.get("estimated_rent") else ""
        area_str = f"{m['area']}m²" if m.get("area") else ""
        typo_str = m.get("typology") or ""
        loc_str = ", ".join(p for p in [m.get("neighborhood"), m.get("city")] if p)
        spread_note = ""
        if (m.get("cluster_size") or 1) > 1 and m.get("price_spread", 0) > 0 and m.get("is_cheapest"):
            spread_note = f" · 💰 €{m['price_spread']:,} cheaper than rival agency"
        lines.append(
            f"• {badge}: *{typo_str} {area_str}* in {loc_str} — *{price_str}* "
            f"({yield_str}{' ' + est_str if est_str else ''}){spread_note}\n  {m['url']}"
        )
    if len(matches) > 15:
        lines.append(f"\n…and {len(matches) - 15} more matching listings.")
    return "\n".join(lines)
