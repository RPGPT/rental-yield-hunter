"""Shared Portuguese typology (T0, T1, T2, …) parsing helpers."""

from __future__ import annotations

import re
from typing import Optional

from word2number import w2n

_TYPOLOGY_RE = re.compile(r"\bT\s*(\d+)\b", re.IGNORECASE)


def typology_from_title(title: str) -> Optional[str]:
    """Extract typology from a listing title (e.g. 'T2', 'T 4')."""
    if not title:
        return None
    match = _TYPOLOGY_RE.search(title)
    return f"T{match.group(1)}" if match else None


def rooms_word_to_typology(value: Optional[str]) -> Optional[str]:
    """Convert Imovirtual room count (includes living room: 'THREE' -> 'T2') to typology."""
    if not value:
        return None
    if value.isdigit():
        return f"T{int(value) - 1}"
    try:
        n = w2n.word_to_num(value.lower())
        return f"T{n - 1}"
    except ValueError:
        return None


def rooms_int_to_typology(rooms) -> Optional[str]:
    """Convert direct bedroom count (e.g. ERA `Rooms` = 2 -> 'T2') to typology."""
    if rooms is None:
        return None
    try:
        return f"T{int(rooms)}"
    except (ValueError, TypeError):
        return None
