"""Physical-apartment deduplication & cross-agency price arbitrage clustering.

Groups active buy listings across sources (Imovirtual, ERA, Casa Sapo) and agencies that
represent the same underlying physical apartment so the frontend can collapse duplicates
and surface multi-agency price spreads (e.g. "€185k on ERA vs €195k on Imovirtual").
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

from word2number import w2n

from yieldhunter.analysis.rented import strip_accents

_FLOOR_ZERO = {"0", "rc", "r/c", "res do chao", "res-do-chao", "ground_floor", "ground", "terreo"}
_FLOOR_ORDINALS = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
    "above_tenth": "11+",
    "basement": "-1",
    "sub_basement": "-2",
    "attic": "attic",
    "mansarda": "attic",
    "recuado": "top",
}
_FLOOR_NUM_RE = re.compile(r"(-?\d+)")

_STREET_RE = re.compile(
    r"\b((?:rua|avenida|av\.?|travessa|praceta|praca|largo|estrada|alameda|calcada|beco)\s+"
    r"[a-z0-9\s.'-]{3,45})",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[a-z0-9]{4,}")
_STOPWORDS = {
    "apartamento",
    "andar",
    "venda",
    "comprar",
    "imovel",
    "porto",
    "gaia",
    "vila",
    "nova",
    "maia",
    "matosinhos",
    "ermesinde",
    "alfena",
    "penafiel",
    "paredes",
    "pacos",
    "ferreira",
    "valongo",
    "quartos",
    "quarto",
    "sala",
    "cozinha",
    "banho",
    "casas",
    "casa",
    "suite",
    "varanda",
    "garagem",
    "lugar",
    "elevador",
    "excelente",
    "oportunidade",
    "localizado",
    "localizacao",
    "zona",
    "perto",
    "junto",
    "servicos",
    "transportes",
    "comercio",
    "escolas",
    "acessos",
    "composto",
    "constituido",
    "inserido",
    "predio",
    "edificio",
    "boas",
    "areas",
    "area",
    "exposicao",
    "solar",
    "visita",
    "marque",
    "para",
    "com",
    "sem",
    "mais",
    "muito",
    "bem",
    "bom",
    "estado",
    "piso",
}


def normalize_floor(floor: Optional[str]) -> Optional[str]:
    if floor is None:
        return None
    norm = strip_accents(str(floor).strip().lower()).replace("floor_", "")
    if not norm:
        return None
    if norm in _FLOOR_ZERO:
        return "0"
    if norm in _FLOOR_ORDINALS:
        return _FLOOR_ORDINALS[norm]
    m = _FLOOR_NUM_RE.search(norm)
    if m:
        return m.group(1)
    try:
        return str(w2n.word_to_num(norm.replace("_", " ")))
    except ValueError:
        return norm


def extract_street(location: Optional[str], title: Optional[str] = None) -> Optional[str]:
    for raw in (location, title):
        if not raw:
            continue
        cleaned = strip_accents(raw.lower())
        for part in cleaned.split(","):
            m = _STREET_RE.search(part.strip())
            if m:
                s = re.sub(r"\bav\.?\s+", "avenida ", m.group(1))
                s = re.sub(r"\s+", " ", s).strip(" .-")
                return s
    return None


def distinctive_tokens(title: Optional[str], description: Optional[str]) -> set[str]:
    txt = strip_accents(f"{title or ''} {description or ''}".lower())
    return {tok for tok in _TOKEN_RE.findall(txt) if tok not in _STOPWORDS and not tok.isdigit()}


def _are_same_apartment(a: dict, b: dict) -> bool:
    area_a, area_b = a["area"], b["area"]
    price_a, price_b = a["price"], b["price"]

    # 1. Tight area tolerance: ±max(2 m², 2%)
    max_area_diff = max(2, round(0.02 * min(area_a, area_b)))
    if abs(area_a - area_b) > max_area_diff:
        return False

    # 2. Realistic multi-agency price spread: <= 12%
    lo_p, hi_p = min(price_a, price_b), max(price_a, price_b)
    if lo_p <= 0 or hi_p > lo_p * 1.12:
        return False

    # 3. Explicit floor conflict check
    fa, fb = a["norm_floor"], b["norm_floor"]
    if fa is not None and fb is not None and fa != fb:
        return False

    # 4. Explicit street conflict check
    sa, sb = a["street"], b["street"]
    if sa and sb and sa != sb and sa not in sb and sb not in sa:
        return False

    # 5. Require strong identity evidence
    # (a) Same street + matching/unknown floor + tight area
    if sa and sb and (sa == sb or sa in sb or sb in sa) and abs(area_a - area_b) <= 2:
        return True

    # (b) Strong distinctive text overlap (shared landmarks / building details)
    toks_a, toks_b = a["tokens"], b["tokens"]
    if len(toks_a) >= 5 and len(toks_b) >= 5:
        inter = len(toks_a & toks_b)
        if inter >= 5:
            union = len(toks_a | toks_b)
            if union > 0 and (inter / union) >= 0.45:
                return True

    # (c) Cross-source exact signature (ERA/CasaSapo vs Imovirtual): exact ±1 m² area,
    #     matching explicit floor, matching garage flag, and <= 5% price difference
    if (
        a["source"] != b["source"]
        and fa is not None
        and fb is not None
        and fa == fb
        and abs(area_a - area_b) <= 1
        and a.get("has_garage") == b.get("has_garage")
        and hi_p <= lo_p * 1.05
    ):
        return True

    return False


def build_listing_clusters(listings: list[dict]) -> list[dict]:
    """Cluster normalized buy listing dicts and return ``listing_clusters`` row dicts."""
    if not listings:
        return []

    by_bucket: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    unbucketed: list[dict] = []

    for item in listings:
        city = item.get("city")
        neighborhood = item.get("neighborhood") or city
        typology = item.get("typology")
        area = item.get("area")
        price = item.get("price")
        if not city or not typology or not area or area <= 0 or not price or price <= 0:
            if price and price > 0:
                unbucketed.append(item)
            continue

        enriched = {
            **item,
            "norm_floor": normalize_floor(item.get("floor")),
            "street": extract_street(item.get("location"), item.get("title")),
            "tokens": distinctive_tokens(item.get("title"), item.get("description")),
        }
        by_bucket[(city, neighborhood or city, typology)].append(enriched)

    output: list[dict] = []

    for group in by_bucket.values():
        n = len(group)
        parent = list(range(n))
        members_map: dict[int, list[int]] = {i: [i] for i in range(n)}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(n):
            for j in range(i + 1, n):
                ri, rj = find(i), find(j)
                if ri == rj:
                    continue
                if not _are_same_apartment(group[i], group[j]):
                    continue

                # Enforce cluster-wide invariants (no transitive floor/street conflicts or drift)
                combined_idxs = members_map[ri] + members_map[rj]
                floors = {group[k]["norm_floor"] for k in combined_idxs if group[k]["norm_floor"] is not None}
                if len(floors) > 1:
                    continue
                streets = [group[k]["street"] for k in combined_idxs if group[k]["street"]]
                if len(set(streets)) > 1:
                    base_st = min(streets, key=len)
                    if not all(base_st in st for st in streets):
                        continue
                areas = [group[k]["area"] for k in combined_idxs]
                prices = [group[k]["price"] for k in combined_idxs]
                if max(areas) - min(areas) > max(3, round(0.03 * min(areas))):
                    continue
                if max(prices) > min(prices) * 1.15:
                    continue

                parent[rj] = ri
                members_map[ri].extend(members_map.pop(rj))

        for comp_idxs in members_map.values():
            comp = [group[k] for k in comp_idxs]
            cluster_id = f"cluster-{min(m['id'] for m in comp)}"
            min_p = min(m["price"] for m in comp)
            max_p = max(m["price"] for m in comp)
            spread = max_p - min_p
            spread_pct = round(spread / max_p, 4) if max_p > 0 else 0.0
            srcs = sorted({m["source"] for m in comp})
            size = len(comp)

            for m in comp:
                output.append(
                    {
                        "listing_id": m["id"],
                        "cluster_id": cluster_id,
                        "cluster_size": size,
                        "cluster_min_price": min_p,
                        "cluster_max_price": max_p,
                        "price_spread": spread,
                        "price_spread_pct": spread_pct,
                        "is_cheapest": m["price"] == min_p,
                        "sources": srcs,
                    }
                )

    for m in unbucketed:
        p = m["price"]
        output.append(
            {
                "listing_id": m["id"],
                "cluster_id": f"cluster-{m['id']}",
                "cluster_size": 1,
                "cluster_min_price": p,
                "cluster_max_price": p,
                "price_spread": 0,
                "price_spread_pct": 0.0,
                "is_cheapest": True,
                "sources": [m["source"]],
            }
        )

    return output
