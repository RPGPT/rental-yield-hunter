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
    "Paços de Ferreira": (
        "arrendar/apartamento/pacos-de-ferreira/",
        "pt/resultados/arrendar/apartamento/porto/pacos-de-ferreira.json",
    ),
    "Penafiel": (
        "arrendar/apartamento/penafiel/",
        "pt/resultados/arrendar/apartamento/porto/penafiel.json",
    ),
    "Paredes": (
        "arrendar/apartamento/paredes/",
        "pt/resultados/arrendar/apartamento/porto/paredes.json",
    ),
    "Ermesinde": (
        "arrendar/apartamento/porto/valongo/ermesinde/",
        "pt/resultados/arrendar/apartamento/porto/valongo/ermesinde.json",
    ),
    "Alfena": (
        "arrendar/apartamento/porto/valongo/alfena/",
        "pt/resultados/arrendar/apartamento/porto/valongo/alfena.json",
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
