MAX_PRICE = 405_000
MIN_PRICE = 50_000
MAX_RENTAL_PRICE = 4_000
MIN_RENTAL_PRICE = 300
REQUEST_DELAY = 2

SUPPORTED_CITIES = [
    "Porto",
    "Matosinhos",
    "Vila Nova de Gaia",
    "Maia",
    "Paços de Ferreira",
    "Penafiel",
    "Paredes",
    "Ermesinde",
    "Alfena",
]

# Freguesias of Valongo scraped as their own "city" (stored city = the freguesia name).
PARISH_CITIES = {"Ermesinde", "Alfena"}

RENTED_KEYWORDS = [
    "arrendado",
    "inquilino",
    "arrendamento",
    "renda",
    "rented",
    "tenant",
    "alugado",
    "contrato de aluguer",
]
