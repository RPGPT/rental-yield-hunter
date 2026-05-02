from config import TENANT_KEYWORDS


def is_rented(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in TENANT_KEYWORDS)
