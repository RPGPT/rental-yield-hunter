"""CLI entrypoint shim — delegates to ``yieldhunter.cli`` and re-exports pipeline entrypoints."""

from yieldhunter.cli import main
from yieldhunter.pipeline import (
    run_extract_contracts,
    run_refresh_clusters,
    run_refresh_estimates,
    run_send_alerts,
    scrape_all,
    scrape_city,
)
from yieldhunter.sources.registry import SCRAPERS

__all__ = [
    "SCRAPERS",
    "main",
    "run_extract_contracts",
    "run_refresh_clusters",
    "run_refresh_estimates",
    "run_send_alerts",
    "scrape_all",
    "scrape_city",
]

if __name__ == "__main__":
    main()
