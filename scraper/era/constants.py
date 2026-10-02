SOURCE = "era"
BASE_URL = "https://www.era.pt/"
SEARCH_API_PATH = "API/ServicesModule/Property/Search"

# Default module/tab IDs from the search page; fetched dynamically but these
# serve as a fallback if the page regex fails.
MODULE_ID = "410"
TAB_ID = "36"

# Detail page module/tab IDs (renderPropertyDetail component)
DETAIL_MODULE_ID = "641"
DETAIL_TAB_ID = "256"

BUSINESS_TYPE_BUY = 1
BUSINESS_TYPE_RENT = 2

# Maps city name → (location_id, buy_search_path)
# location_id: ERA internal district-municipality code (district-municipality)
# buy_search_path: used to load the page and extract a fresh CSRF token
CITY_CONFIG: dict[str, tuple[str, str]] = {
    "Porto": ("13-12", "comprar/apartamentos/porto"),
    "Matosinhos": ("13-08", "comprar/apartamentos/matosinhos"),
    "Vila Nova de Gaia": ("13-17", "comprar/apartamentos/vila-nova-de-gaia"),
    "Maia": ("13-06", "comprar/apartamentos/maia"),
    "Paços de Ferreira": ("13-09", "comprar/apartamentos/pacos-de-ferreira"),
    "Paredes": ("13-10", "comprar/apartamentos/paredes"),
    "Penafiel": ("13-11", "comprar/apartamentos/penafiel"),
    # Ermesinde and Alfena are freguesias of Valongo; ERA only exposes the municipality
    "Ermesinde": ("13-15", "comprar/apartamentos/valongo"),
    "Alfena": ("13-15", "comprar/apartamentos/valongo"),
}

# ERA's Localization suffix is often the district ("Meixomil, Porto") rather than the
# municipality, so for these cities we trust the municipality-scoped search instead.
SEARCH_SCOPED_CITIES = {"Paços de Ferreira", "Paredes", "Penafiel", "Ermesinde", "Alfena"}

PROPERTY_TYPE_MAP = {
    "Apartamento": "apartment",
    "Moradia": "house",
    "Moradia Isolada": "house",
    "Moradia Geminada": "house",
    "Moradia em Banda": "house",
    "Terreno": "land",
    "Garagem": "garage",
    "Armazém": "warehouse",
}
