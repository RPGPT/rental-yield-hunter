SOURCE = "imovirtual"
BASE_URL = "https://www.imovirtual.com/"

# Maps city name → (search_path, api_path)
# search_path: used to fetch buildId from the HTML page
# api_path:    used for the __NEXT_DATA__ JSON endpoint
CITY_PATHS: dict[str, tuple[str, str]] = {
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

ESTATE_MAP = {
    "FLAT": "apartment",
    "HOUSE": "house",
    "TERRAIN": "land",
    "GARAGE": "garage",
    "WAREHOUSE": "warehouse",
}

ROOMS_MAP = {
    "ONE": "T1",
    "TWO": "T2",
    "THREE": "T3",
    "FOUR": "T4",
    "FIVE_OR_MORE": "T5+",
}
