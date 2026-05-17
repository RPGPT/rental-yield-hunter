"""Deterministic rental-contract detail extractor.

Extracts **current rent amount** (EUR) and **contract expiry date** from
free-text listing descriptions written in Portuguese or English.

Uses only local, free tools:
- ``re`` for rent amount extraction (anchor-phrase proximity)
- ``dateparser`` for multilingual date parsing

No LLM / paid API is involved.

Usage::

    from scraper.contract_extractor import extract_rent_and_expiry

    result = extract_rent_and_expiry(
        "Arrendado por 800€/mês com contrato até fevereiro de 2027."
    )
    # {
    #     "current_rent_amount": 800.0,
    #     "currency": "EUR",
    #     "contract_expiry_date": "2027-02-28",
    #     "raw_rent_text": "800€",
    #     "raw_expiry_text": "fevereiro de 2027",
    #     "confidence": 0.9,
    # }
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from typing import Optional

import dateparser

# ── Anchor phrases ────────────────────────────────────────────────────────────
# Sorted longest-first so greedy matching picks the most specific anchor.

_RENT_ANCHORS_PT = [
    "renda atual",
    "renda mensal",
    "arrendado por",
    "arrendadas por",
    "arrendada por",
    "arrendados por",
    "renda de",
    "renda",
    "mensais",
    "por mes",
]

_RENT_ANCHORS_EN = [
    "current rent",
    "rented for",
    "rented at",
    "monthly rent",
    "per month",
    "rent",
]

_EXPIRY_ANCHORS_PT = [
    "contrato de arrendamento valido ate",
    "contrato em vigor ate",
    "contrato vigente ate",
    "contrato valido ate",
    "contrato ate",
    "valido ate",
    "vigente ate",
    "arrendado ate",
    "arrendada ate",
    "arrendamento ate",
    "ate",
]

_EXPIRY_ANCHORS_EN = [
    "valid until",
    "lease until",
    "rented until",
    "contract until",
    "expires on",
    "until",
]

# ── Text helpers ──────────────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITIES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">"}


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(entity, char)
    return _HTML_TAG_RE.sub(" ", text)


def _strip_accents(text: str) -> str:
    """Remove diacritics for accent-insensitive matching."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")


# ── Number-format helpers ─────────────────────────────────────────────────────


def _normalize_amount(raw: str) -> Optional[float]:
    """Parse a euro amount from varied formats.

    Handles: ``800``, ``870.00``, ``1,200``, ``1.200,00``, ``1 200``.
    Returns *None* when the string doesn't look like a valid number.
    """
    s = raw.strip().replace("\u00a0", " ")

    # European: 1.200,00  →  1200.00
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d{1,2})?$", s):
        s = s.replace(".", "").replace(",", ".")
        return float(s)

    # English: 1,200.00  →  1200.00
    if re.match(r"^\d{1,3}(,\d{3})+(\.\d{1,2})?$", s):
        s = s.replace(",", "")
        return float(s)

    # Simple: 800 | 870.00 | 800,50
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


# ── Euro-amount regex ─────────────────────────────────────────────────────────
# Matches patterns like: €800  800€  € 1,200.00  1.200,00 €  870.00 euros
_EURO_RE = re.compile(
    r"""
    (?:€\s*)                          # € prefix
    (\d[\d\s.,]*)                     # capture the number
    |
    (\d[\d\s.,]*)                     # capture the number
    \s*(?:€|euros?\b)                 # € suffix or "euro(s)"
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _find_euro_amounts(text: str) -> list[tuple[float, int, int, str]]:
    """Return ``[(amount, start, end, raw_text), ...]`` for every €-value in *text*."""
    results = []
    for m in _EURO_RE.finditer(text):
        raw_digits = m.group(1) or m.group(2)
        if not raw_digits:
            continue
        amount = _normalize_amount(raw_digits)
        if amount is not None and amount > 0:
            results.append((amount, m.start(), m.end(), m.group(0).strip()))
    return results


# ── Rent extraction ───────────────────────────────────────────────────────────

_MONTHLY_WORDS = re.compile(
    r"\b(?:m[eê]s|mensais?|mensal|monthly|per\s+month|p/m|/m[eê]s|/mes)\b",
    re.IGNORECASE,
)

_MULTIPLIER_RE = re.compile(
    r"\b(?:cada\s+uma|cada\s+um|each)\b",
    re.IGNORECASE,
)

_COUNT_BEFORE_RE = re.compile(
    r"\b(\d+|duas|dois|três|tres|quatro|cinco|two|three|four|five)\s+"
    r"(?:casas?|apartamentos?|frações|fracoes|unidades?|propriedades?|"
    r"properties|units?|flats?|houses?)\b",
    re.IGNORECASE,
)

_WORD_TO_NUM = {
    "duas": 2,
    "dois": 2,
    "two": 2,
    "três": 3,
    "tres": 3,
    "three": 3,
    "quatro": 4,
    "four": 4,
    "cinco": 5,
    "five": 5,
}


def _parse_unit_count(text: str) -> int:
    """Detect multipliers like 'duas casas ... cada uma'."""
    m = _COUNT_BEFORE_RE.search(text)
    if not m:
        return 1
    # Only apply multiplier if "cada uma/each" appears
    if not _MULTIPLIER_RE.search(text):
        return 1
    raw = m.group(1)
    if raw.isdigit():
        return int(raw)
    return _WORD_TO_NUM.get(raw.lower(), 1)


def _score_rent_candidate(
    amount: float,
    pos_start: int,
    pos_end: int,
    text_lower: str,
) -> float:
    """Score how likely an euro amount is the *current monthly rent*.

    Higher score = more likely.  Returns 0.0 if definitely not rent.
    """
    score = 0.0
    window = 80  # characters to search around the match

    left_ctx = text_lower[max(0, pos_start - window) : pos_start]
    right_ctx = text_lower[pos_end : pos_end + window]
    neighbourhood = left_ctx + " " + right_ctx
    # Normalize accents for anchor matching
    neighbourhood_norm = _strip_accents(neighbourhood)

    # Negative signals — per-m² prices, condominium fees
    tight_right = _strip_accents(text_lower[pos_end : pos_end + 10])
    tight_left = _strip_accents(text_lower[max(0, pos_start - 30) : pos_start])
    if re.search(r"/m[²2]|€/m|eur.*m[²2]", tight_right):
        return 0.0
    if re.search(r"preco\s*por\s*m[²2]|price\s*per\s*m[²2]|condominio|condominium", tight_left):
        return 0.0

    # Monthly wording nearby is a strong signal
    if _MONTHLY_WORDS.search(neighbourhood):
        score += 0.5

    # Anchor phrase nearby
    all_anchors = _RENT_ANCHORS_PT + _RENT_ANCHORS_EN
    for anchor in all_anchors:
        if anchor in neighbourhood_norm:
            score += 0.4
            break

    # Reasonable monthly rent range for Portugal (50–10 000 €)
    if 50 <= amount <= 10_000:
        score += 0.1
    else:
        return 0.0  # definitely not a monthly rent

    return score


def _extract_rent(text: str) -> tuple[Optional[float], Optional[str], float]:
    """Return ``(amount, raw_text, confidence)``."""
    amounts = _find_euro_amounts(text)
    if not amounts:
        return None, None, 0.0

    text_lower = text.lower()
    scored = []
    for amount, start, end, raw in amounts:
        s = _score_rent_candidate(amount, start, end, text_lower)
        if s > 0:
            scored.append((s, amount, raw))

    if not scored:
        return None, None, 0.0

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_amount, best_raw = scored[0]

    # Multiply if "duas casas … cada uma"
    multiplier = _parse_unit_count(text_lower)
    final_amount = best_amount * multiplier

    confidence = min(1.0, best_score)
    return final_amount, best_raw, confidence


# ── Expiry-date extraction ────────────────────────────────────────────────────

_ALL_EXPIRY_ANCHORS = sorted(
    _EXPIRY_ANCHORS_PT + _EXPIRY_ANCHORS_EN,
    key=len,
    reverse=True,
)


def _extract_expiry(text: str) -> tuple[Optional[str], Optional[str], float]:
    """Return ``(iso_date_str, raw_text, confidence)``."""
    # Strip accents for matching so "até"/"ate" and "válido"/"valido" all work.
    # We use the normalised text for both searching and chunk extraction because
    # accent removal doesn't change character positions in the NFC-normalised
    # string, and dateparser handles accent-free Portuguese just fine.
    text_norm = _strip_accents(text.lower())

    for anchor in _ALL_EXPIRY_ANCHORS:
        idx = text_norm.find(anchor)
        if idx == -1:
            continue

        # Grab a window after the anchor
        after_start = idx + len(anchor)
        after = text_norm[after_start : after_start + 60].strip()
        # Remove leading punctuation / whitespace
        after = re.sub(r"^[\s:.,;]+", "", after)
        # Take the first meaningful chunk (up to a period, comma-clause, or newline)
        chunk = re.split(r"[.\n]", after)[0].strip()
        # Trim trailing junk like ", com contrato..." but don't match inside words
        chunk = re.sub(r"\s*(?:,|;)\s.*$", "", chunk, flags=re.IGNORECASE).strip()
        chunk = re.sub(r"\s+(?:com|and)\s+.*$", "", chunk, flags=re.IGNORECASE).strip()
        # Trim trailing monetary/prepositional phrases: "for €870", "por 800€"
        chunk = re.sub(r"\s+(?:for|por|with)\s+[€\d].*$", "", chunk, flags=re.IGNORECASE).strip()
        # Trim anything after a 4-digit year (e.g. "2027 visitas suspensas" → "2027")
        chunk = re.sub(r"(\b\d{4}\b)\s+[a-z].*$", r"\1", chunk, flags=re.IGNORECASE).strip()

        if not chunk or len(chunk) < 4:
            continue

        parsed = dateparser.parse(
            chunk,
            languages=["pt", "en"],
            settings={
                "PREFER_DATES_FROM": "future",
                "REQUIRE_PARTS": ["month", "year"],
            },
        )
        if parsed and parsed.year >= 2024:
            # If the original text only has month+year (no day digit in chunk),
            # normalise to last day of month.
            has_day = bool(re.search(r"\b\d{1,2}\b", chunk) and re.search(r"\b\d{4}\b", chunk))
            if not has_day:
                day = _last_day_of_month(parsed.year, parsed.month)
                parsed = parsed.replace(day=day)
            iso = parsed.date().isoformat()
            # Higher confidence for longer / more specific anchors
            conf = 0.9 if len(anchor) > 5 else 0.7
            return iso, chunk, conf

    return None, None, 0.0


# ── Public API ────────────────────────────────────────────────────────────────


def extract_rent_and_expiry(text: str) -> dict:
    """Extract current rent (EUR) and contract expiry date from *text*.

    Handles raw HTML input (tags are stripped automatically).

    Returns a dict with:
    - ``current_rent_amount``: float or None
    - ``currency``: always ``"EUR"``
    - ``contract_expiry_date``: ISO date string or None
    - ``raw_rent_text``: matched substring or None
    - ``raw_expiry_text``: matched substring or None
    - ``confidence``: float 0.0–1.0 (aggregate)
    """
    text = _strip_html(text)
    # Collapse whitespace left after HTML removal
    text = re.sub(r"\s+", " ", text).strip()

    rent_amount, rent_raw, rent_conf = _extract_rent(text)
    expiry_date, expiry_raw, expiry_conf = _extract_expiry(text)

    # Aggregate confidence: average of non-zero fields
    confs = [c for c in (rent_conf, expiry_conf) if c > 0]
    confidence = sum(confs) / len(confs) if confs else 0.0

    return {
        "current_rent_amount": rent_amount,
        "currency": "EUR",
        "contract_expiry_date": expiry_date,
        "raw_rent_text": rent_raw,
        "raw_expiry_text": expiry_raw,
        "confidence": round(confidence, 2),
    }
