"""Imovirtual URL paths and estate mappings."""

from __future__ import annotations

SOURCE = "imovirtual"
BASE_URL = "https://www.imovirtual.com/"

BUY_CITY_PATHS: dict[str, tuple[str, str]] = {
    "Porto": (
        "comprar/apartamento/porto/",
        "pt/resultados/comprar/apartamento/porto/porto.json",
    ),
    "Matosinhos": (
        "comprar/apartamento/matosinhos/",
        "pt/resultados/comprar/apartamento/porto/matosinhos.json",
    ),
    "Vila Nova de Gaia": (
        "comprar/apartamento/vila-nova-de-gaia/",
        "pt/resultados/comprar/apartamento/porto/vila-nova-de-gaia.json",
    ),
    "Maia": (
        "comprar/apartamento/maia/",
        "pt/resultados/comprar/apartamento/porto/maia.json",
    ),
    "Paços de Ferreira": (
        "comprar/apartamento/pacos-de-ferreira/",
        "pt/resultados/comprar/apartamento/porto/pacos-de-ferreira.json",
    ),
    "Penafiel": (
        "comprar/apartamento/penafiel/",
        "pt/resultados/comprar/apartamento/porto/penafiel.json",
    ),
    "Paredes": (
        "comprar/apartamento/paredes/",
        "pt/resultados/comprar/apartamento/porto/paredes.json",
    ),
    "Ermesinde": (
        "comprar/apartamento/porto/valongo/ermesinde/",
        "pt/resultados/comprar/apartamento/porto/valongo/ermesinde.json",
    ),
    "Alfena": (
        "comprar/apartamento/porto/valongo/alfena/",
        "pt/resultados/comprar/apartamento/porto/valongo/alfena.json",
    ),
}

RENTAL_CITY_PATHS: dict[str, tuple[str, str]] = {
    city: (
        search_path.replace("comprar/", "arrendar/", 1),
        api_path.replace("/comprar/", "/arrendar/", 1),
    )
    for city, (search_path, api_path) in BUY_CITY_PATHS.items()
}

CITY_PATHS = BUY_CITY_PATHS

ESTATE_MAP: dict[str, str] = {
    "FLAT": "apartment",
    "HOUSE": "house",
    "TERRAIN": "land",
    "GARAGE": "garage",
    "WAREHOUSE": "warehouse",
}
