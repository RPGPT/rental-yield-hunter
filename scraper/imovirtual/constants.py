SOURCE = "imovirtual"
BASE_URL = "https://www.imovirtual.com/"

# Maps city name → (search_path, api_path)
# search_path: used to fetch buildId from the HTML page
# api_path:    used for the __NEXT_DATA__ JSON endpoint
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
}

RENTAL_CITY_PATHS: dict[str, tuple[str, str]] = {
    "Porto": (
        "arrendar/apartamento/porto/",
        "pt/resultados/arrendar/apartamento/porto/porto.json",
    ),
    "Matosinhos": (
        "arrendar/apartamento/matosinhos/",
        "pt/resultados/arrendar/apartamento/porto/matosinhos.json",
    ),
    "Vila Nova de Gaia": (
        "arrendar/apartamento/vila-nova-de-gaia/",
        "pt/resultados/arrendar/apartamento/porto/vila-nova-de-gaia.json",
    ),
    "Maia": (
        "arrendar/apartamento/maia/",
        "pt/resultados/arrendar/apartamento/porto/maia.json",
    ),
}

# Backward-compatible alias
CITY_PATHS = BUY_CITY_PATHS

ESTATE_MAP = {
    "FLAT": "apartment",
    "HOUSE": "house",
    "TERRAIN": "land",
    "GARAGE": "garage",
    "WAREHOUSE": "warehouse",
}
