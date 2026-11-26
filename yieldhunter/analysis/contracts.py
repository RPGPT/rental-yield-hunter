"""Deterministic rental-contract detail extractor (Portuguese & English).

Extracts **current monthly rent** (EUR) and **contract expiry date** from
free-text listing descriptions using anchor-phrase proximity and ``dateparser``.
No external or paid LLM APIs are used.
"""

from __future__ import annotations

import calendar
import re
from typing import Optional

import dateparser

from yieldhunter.analysis.rented import strip_accents as _strip_accents

_RENT_ANCHORS = [
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
    "current rent",
    "rented for",
    "rented at",
    "monthly rent",
    "per month",
    "rent",
]

_ALL_EXPIRY_ANCHORS = sorted(
    [
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
        "valid until",
        "lease until",
        "rented until",
        "contract until",
        "expires on",
        "until",
    ],
    key=len,
    reverse=True,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITIES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">"}
_EU_THOUSANDS_RE = re.compile(r"^\d{1,3}(\.\d{3})+(,\d{1,2})?$")
_EN_THOUSANDS_RE = re.compile(r"^\d{1,3}(,\d{3})+(\.\d{1,2})?$")

_EURO_RE = re.compile(
    r"""
    (?:€\s*)
    (\d[\d\s.,]*)
    |
    (\d[\d\s.,]*)
    \s*(?:€|euros?\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MONTHLY_WORDS = re.compile(
    r"\b(?:m[eê]s|mensais?|mensal|monthly|per\s+month|p/m|/m[eê]s|/mes)\b",
    re.IGNORECASE,
)
_MULTIPLIER_RE = re.compile(r"\b(?:cada\s+uma|cada\s+um|each)\b", re.IGNORECASE)
_COUNT_BEFORE_RE = re.compile(
    r"\b(\d+|duas|dois|três|tres|quatro|cinco|two|three|four|five)\s+"
    r"(?:casas?|apartamentos?|frações|fracoes|unidades?|propriedades?|"
    r"properties|units?|flats?|houses?)\b",
    re.IGNORECASE,
)
_NEG_RIGHT_RE = re.compile(r"/m[²2]|€/m|eur.*m[²2]")
_NEG_LEFT_RE = re.compile(r"preco\s*por\s*m[²2]|price\s*per\s*m[²2]|condominio|condominium")

_LEAD_PUNCT_RE = re.compile(r"^[\s:.,;]+")
_CLAUSE_SPLIT_RE = re.compile(r"[.\n]")
_TRAIL_COMMA_RE = re.compile(r"\s*(?:,|;)\s.*$", re.IGNORECASE)
_TRAIL_CONJ_RE = re.compile(r"\s+(?:com|and)\s+.*$", re.IGNORECASE)
_TRAIL_MONEY_RE = re.compile(r"\s+(?:for|por|with)\s+[€\d].*$", re.IGNORECASE)
_AFTER_YEAR_RE = re.compile(r"(\b\d{4}\b)\s+[a-z].*$", re.IGNORECASE)
_TRAIL_BRACKET_RE = re.compile(r"[\s)\]]+$")
_YEAR_ONLY_RE = re.compile(r"\d{4}")
_DAY_DIGIT_RE = re.compile(r"\b\d{1,2}\b")
_FOUR_DIGIT_YEAR_RE = re.compile(r"\b\d{4}\b")
_WS_RE = re.compile(r"\s+")

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


def _strip_html(text: str) -> str:
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(entity, char)
    return _HTML_TAG_RE.sub(" ", text)


def _normalize_amount(raw: str) -> Optional[float]:
    """Parse a euro amount from European, English, or plain number formats."""
    s = raw.strip().replace("\u00a0", " ")
    if _EU_THOUSANDS_RE.match(s):
        return float(s.replace(".", "").replace(",", "."))
    if _EN_THOUSANDS_RE.match(s):
        return float(s.replace(",", ""))
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


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


def _parse_unit_count(text: str) -> int:
    m = _COUNT_BEFORE_RE.search(text)
    if not m or not _MULTIPLIER_RE.search(text):
        return 1
    raw = m.group(1)
    return int(raw) if raw.isdigit() else _WORD_TO_NUM.get(raw.lower(), 1)


def _score_rent_candidate(amount: float, pos_start: int, pos_end: int, text_lower: str) -> float:
    if not (50 <= amount <= 10_000):
        return 0.0

    tight_right = _strip_accents(text_lower[pos_end : pos_end + 10])
    tight_left = _strip_accents(text_lower[max(0, pos_start - 30) : pos_start])
    if _NEG_RIGHT_RE.search(tight_right) or _NEG_LEFT_RE.search(tight_left):
        return 0.0

    window = 80
    neighbourhood = text_lower[max(0, pos_start - window) : pos_start] + " " + text_lower[pos_end : pos_end + window]
    neighbourhood_norm = _strip_accents(neighbourhood)

    score = 0.1
    if _MONTHLY_WORDS.search(neighbourhood):
        score += 0.5
    if any(anchor in neighbourhood_norm for anchor in _RENT_ANCHORS):
        score += 0.4

    return score


def _extract_rent(text: str) -> tuple[Optional[float], Optional[str], float]:
    amounts = _find_euro_amounts(text)
    if not amounts:
        return None, None, 0.0

    text_lower = text.lower()
    scored = [
        (score, amount, raw)
        for amount, start, end, raw in amounts
        if (score := _score_rent_candidate(amount, start, end, text_lower)) > 0
    ]
    if not scored:
        return None, None, 0.0

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_amount, best_raw = scored[0]
    final_amount = best_amount * _parse_unit_count(text_lower)
    return final_amount, best_raw, min(1.0, best_score)


def _extract_expiry(text: str) -> tuple[Optional[str], Optional[str], float]:
    text_norm = _strip_accents(text.lower())

    for anchor in _ALL_EXPIRY_ANCHORS:
        idx = text_norm.find(anchor)
        if idx == -1:
            continue

        after = text_norm[idx + len(anchor) : idx + len(anchor) + 60].strip()
        after = _LEAD_PUNCT_RE.sub("", after)
        chunk = _CLAUSE_SPLIT_RE.split(after)[0].strip()
        chunk = _TRAIL_COMMA_RE.sub("", chunk).strip()
        chunk = _TRAIL_CONJ_RE.sub("", chunk).strip()
        chunk = _TRAIL_MONEY_RE.sub("", chunk).strip()
        chunk = _AFTER_YEAR_RE.sub(r"\1", chunk).strip()
        chunk = _TRAIL_BRACKET_RE.sub("", chunk)

        if not chunk or len(chunk) < 4:
            continue

        year_only = bool(_YEAR_ONLY_RE.fullmatch(chunk))
        parsed = dateparser.parse(
            chunk,
            languages=["pt", "en"],
            settings={
                "PREFER_DATES_FROM": "future",
                "REQUIRE_PARTS": ["year"] if year_only else ["month", "year"],
            },
        )
        if parsed and parsed.year >= 2024:
            if year_only:
                parsed = parsed.replace(month=12, day=31)
            has_day = bool(_DAY_DIGIT_RE.search(chunk) and _FOUR_DIGIT_YEAR_RE.search(chunk))
            if not year_only and not has_day:
                parsed = parsed.replace(day=_last_day_of_month(parsed.year, parsed.month))
            conf = 0.9 if len(anchor) > 5 else 0.7
            return parsed.date().isoformat(), chunk, conf

    return None, None, 0.0


def extract_rent_and_expiry(text: str) -> dict:
    """Extract current rent (EUR) and contract expiry date from *text*."""
    cleaned = _WS_RE.sub(" ", _strip_html(text)).strip()
    rent_amount, rent_raw, rent_conf = _extract_rent(cleaned)
    expiry_date, expiry_raw, expiry_conf = _extract_expiry(cleaned)

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
