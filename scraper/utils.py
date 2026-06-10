import unicodedata

from config import RENTED_KEYWORDS


def is_rented(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in RENTED_KEYWORDS)


def is_lifetime_rent(text: str) -> bool:
    normalized = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return "vitalicio" in stripped or "vitalicia" in stripped
