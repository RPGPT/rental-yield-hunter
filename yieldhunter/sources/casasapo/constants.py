"""Casa Sapo (casa.sapo.pt) URL slugs and scraping constants."""

from __future__ import annotations

SOURCE = "casasapo"
BASE_URL = "https://casa.sapo.pt"

# Polite per-page delay and 429 retry backoffs (Casa Sapo rate-limits un-throttled bursts).
CASASAPO_PAGE_DELAY: float = 3.0
CASASAPO_RETRY_BACKOFFS: tuple[float, ...] = (12.0, 25.0)

# sa=13 scopes searches to Distrito do Porto.
PORTO_DISTRICT_CODE = "13"

CITY_SLUGS: dict[str, str] = {
    "Porto": "porto",
    "Matosinhos": "matosinhos",
    "Vila Nova de Gaia": "vila-nova-de-gaia",
    "Maia": "maia",
    "Paços de Ferreira": "pacos-de-ferreira",
    "Penafiel": "penafiel",
    "Paredes": "paredes",
    "Ermesinde": "valongo/ermesinde",
    "Alfena": "valongo/alfena",
}
