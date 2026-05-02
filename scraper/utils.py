from config import RENTED_KEYWORDS


def is_rented(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in RENTED_KEYWORDS)
