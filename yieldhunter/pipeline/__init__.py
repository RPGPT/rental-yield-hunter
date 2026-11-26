"""Pipeline orchestration subpackage.

Exports are loaded lazily via PEP 562 ``__getattr__`` so stdlib-only entrypoints
such as ``python3 -m yieldhunter.pipeline.stats`` can execute in bare CI
environments without installing third-party dependencies.
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "run_extract_contracts": ("yieldhunter.pipeline.contracts", "run_extract_contracts"),
    "run_refresh_clusters": ("yieldhunter.pipeline.clusters", "run_refresh_clusters"),
    "run_refresh_estimates": ("yieldhunter.pipeline.estimates", "run_refresh_estimates"),
    "run_send_alerts": ("yieldhunter.pipeline.alerts", "run_send_alerts"),
    "scrape_all": ("yieldhunter.pipeline.scrape", "scrape_all"),
    "scrape_city": ("yieldhunter.pipeline.scrape", "scrape_city"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = importlib.import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *_EXPORTS])
