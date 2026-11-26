"""Command-line interface for Rental Yield Hunter."""

from __future__ import annotations

import argparse
import logging
import pathlib
from typing import Optional

from yieldhunter.config import SUPPORTED_CITIES
from yieldhunter.pipeline import (
    run_extract_contracts,
    run_refresh_clusters,
    run_refresh_estimates,
    run_send_alerts,
    scrape_all,
)
from yieldhunter.pipeline.stats import main as summarize_main
from yieldhunter.sources.registry import SCRAPERS


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Rental Yield Hunter")
    ap.add_argument("--source", choices=list(SCRAPERS.keys()), default="imovirtual")
    ap.add_argument(
        "--type",
        dest="listing_type",
        choices=["buy", "rent", "estimates", "contracts", "clusters", "alerts", "summarize"],
        default="buy",
        help="buy/rent scraping, estimates, contracts, clusters, saved-search alerts, or CI summary.",
    )
    ap.add_argument(
        "--city",
        choices=SUPPORTED_CITIES,
        default=None,
        help="City to process. Omit to process all supported cities.",
    )
    ap.add_argument(
        "--parallel",
        action="store_true",
        default=False,
        help="Scrape all cities in parallel using a thread pool.",
    )
    ap.add_argument(
        "--stats-dir",
        default="stats",
        help="Directory containing stats-*.json files when --type summarize is used.",
    )
    return ap


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    args = build_parser().parse_args(argv)

    if args.listing_type == "estimates":
        run_refresh_estimates(city=args.city)
    elif args.listing_type == "contracts":
        run_extract_contracts(city=args.city)
    elif args.listing_type == "clusters":
        run_refresh_clusters(city=args.city)
    elif args.listing_type == "alerts":
        run_send_alerts()
    elif args.listing_type == "summarize":
        summarize_main([str(pathlib.Path(args.stats_dir))])
    else:
        cities = [args.city] if args.city else SUPPORTED_CITIES
        scrape_all(
            source=args.source,
            cities=cities,
            listing_type=args.listing_type,
            parallel=args.parallel,
        )
