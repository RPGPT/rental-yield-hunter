"""Shared HTTP constants for Chrome-impersonated scraping sessions."""

from __future__ import annotations

ACCEPT_LANGUAGE = "pt-PT,pt;q=0.9"
HTML_HEADERS = {
    "Accept": "text/html",
    "Accept-Language": ACCEPT_LANGUAGE,
}
