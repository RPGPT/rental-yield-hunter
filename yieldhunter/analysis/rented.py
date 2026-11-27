"""Detection of tenanted listings and lifetime-rent clauses."""

from __future__ import annotations

import re
import unicodedata

from yieldhunter.config import RENTED_KEYWORDS

_RENTED_RE = re.compile("|".join(re.escape(kw) for kw in RENTED_KEYWORDS), re.IGNORECASE)
_LIFETIME_RE = re.compile(r"vitalici[oa]", re.IGNORECASE)

# Phrases mentioning "arrendamento" / rental terms that do NOT mean the property is currently tenanted:
# - Investment-suitability pitches ("ideal para arrendamento de curta ou longa duração")
# - Agency boilerplate ("Compra/ Venda/ Arrendamento de imóveis")
# - Explicit negations ("não está arrendado", "sem inquilino")
_FALSE_POSITIVE_RE = re.compile(
    r"|".join(
        [
            r"\b(?:ideal|excelente|otim[oa]|perfeit[oa]|destinad[oa]|vocacionad[oa]|pront[oa]|apropriad[oa]|indicad[oa])\s+para\s+(?:o\s+)?(?:mercado\s+de\s+)?arrendamento\b",
            r"\bpara\s+arrendamento\s+(?:de\s+)?(?:curta|longa|media)\s+duracao\b",
            r"\bpara\s+habitacao\s+propria\s+(?:ou|e)\s+(?:para\s+)?arrendamento\b",
            r"\b(?:potencial|mercado|opcao|finalidade|objetivo|investimento)\s+(?:de|para|no)\s+(?:o\s+)?arrendamento\b",
            r"\bcompra\s*[/,]\s*venda\s*[/,]\s*arrendamento\b",
            r"\b(?:venda|compra|mediacao|gestao)\s*(?:e|ou|/)\s*arrendamento\b",
            r"\b(?:nao|sem)\s+(?:esta\s+)?(?:arrendad[oa]|alugad[oa]|inquilinos?|contrato\s+de\s+arrendamento)\b",
        ]
    ),
    re.IGNORECASE,
)


def strip_accents(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def is_rented(text: str) -> bool:
    if not text:
        return False
    cleaned = _FALSE_POSITIVE_RE.sub(" ", strip_accents(text))
    return bool(_RENTED_RE.search(cleaned))


def is_lifetime_rent(text: str) -> bool:
    return bool(_LIFETIME_RE.search(strip_accents(text)))
