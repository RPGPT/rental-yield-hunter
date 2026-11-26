"""Detection of tenanted listings and lifetime-rent clauses."""

from __future__ import annotations

import re
import unicodedata

from yieldhunter.config import RENTED_KEYWORDS

_RENTED_RE = re.compile("|".join(re.escape(kw) for kw in RENTED_KEYWORDS), re.IGNORECASE)
_LIFETIME_RE = re.compile(r"vitalici[oa]", re.IGNORECASE)


def strip_accents(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def is_rented(text: str) -> bool:
    return bool(_RENTED_RE.search(text))


def is_lifetime_rent(text: str) -> bool:
    return bool(_LIFETIME_RE.search(strip_accents(text)))
