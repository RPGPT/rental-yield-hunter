"""Application-wide configuration constants."""

from __future__ import annotations

MAX_PRICE: int = 405_000
MIN_PRICE: int = 50_000
MAX_RENTAL_PRICE: int = 4_000
MIN_RENTAL_PRICE: int = 300
REQUEST_DELAY: float = 2.0

SUPPORTED_CITIES: list[str] = [
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

# Freguesias of Valongo scraped and stored under their parish name rather than "Valongo".
PARISH_CITIES: set[str] = {"Ermesinde", "Alfena"}

RENTED_KEYWORDS: list[str] = [
    "arrendado",
    "inquilino",
    "arrendamento",
    "renda",
    "rented",
    "tenant",
    "alugado",
    "contrato de aluguer",
]

ESTIMATE_MIN_SAMPLES: int = 3
ESTIMATE_AREA_TOLERANCE: float = 0.15
ESTIMATE_AREA_EXPONENT: float = 0.30
ESTIMATE_AREA_SIGMA: float = 0.22
ESTIMATE_INACTIVE_DAYS: int = 60
ESTIMATE_INACTIVE_WEIGHT: float = 0.60
ESTIMATE_OTHER_PARISH_WEIGHT: float = 0.25
INSERT_CHUNK_SIZE: int = 500
