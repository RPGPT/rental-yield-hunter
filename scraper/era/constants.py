SOURCE = "era"
BASE_URL = "https://www.era.pt/"
SEARCH_API_PATH = "API/ServicesModule/Property/Search"

# Default module/tab IDs from the search page; fetched dynamically but these
# serve as a fallback if the page regex fails.
MODULE_ID = "410"
TAB_ID = "36"

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
}

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
