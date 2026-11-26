"""Shared repository utilities (chunking under Postgres bind-parameter limit, URL cleanup)."""

from __future__ import annotations

from typing import Iterator, Optional, Sequence, TypeVar

from yieldhunter.config import INSERT_CHUNK_SIZE

T = TypeVar("T")


def chunks(rows: Sequence[T], size: int = INSERT_CHUNK_SIZE) -> Iterator[Sequence[T]]:
    """Yield slices of *rows* so multi-row inserts stay well under Postgres's 65,535 param limit."""
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def sanitize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    return url.replace("/hpr/", "/")
