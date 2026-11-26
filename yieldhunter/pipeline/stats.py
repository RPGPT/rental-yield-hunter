"""Run-stats JSON persistence and GitHub Actions Markdown summary rendering.

Uses only the Python standard library so CI's ``summarise`` job can execute
``python3 -m yieldhunter.pipeline.stats stats`` without installing dependencies.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Iterable


def city_slug(city: str | None) -> str:
    return city.replace(" ", "-") if city else "all"


def write_stats_file(filename: str, stats: dict, directory: pathlib.Path | None = None) -> pathlib.Path:
    target_dir = directory or pathlib.Path(".")
    path = target_dir / filename
    path.write_text(json.dumps(stats), encoding="utf-8")
    return path


def _merge_by_city(rows: Iterable[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for r in rows:
        m = merged.setdefault(
            r["city"],
            {
                "city": r["city"],
                "type": r.get("type"),
                "fetched": 0,
                "rented": 0,
                "price_changes": 0,
            },
        )
        m["fetched"] += r.get("fetched", 0)
        m["rented"] += r.get("rented", 0)
        m["price_changes"] += r.get("price_changes", 0)
    return sorted(merged.values(), key=lambda item: item["city"])


def render_job_summary(stats_dir: pathlib.Path) -> str:
    all_rows = (
        sorted(
            (json.loads(f.read_text(encoding="utf-8")) for f in stats_dir.glob("stats-*.json")),
            key=lambda r: r.get("city") or "",
        )
        if stats_dir.exists()
        else []
    )
    if not all_rows:
        return "## 🏠 Scrape Summary\n\nNo stats available — all city jobs may have failed.\n"

    chunks: list[str] = ["## 🏠 Scrape Summary\n\n"]

    buy_rows = _merge_by_city(r for r in all_rows if r.get("type") == "buy")
    if buy_rows:
        total_fetched = sum(r["fetched"] for r in buy_rows)
        total_rented = sum(r.get("rented", 0) for r in buy_rows)
        total_changes = sum(r["price_changes"] for r in buy_rows)
        chunks.append("### 🛒 Buy\n\n")
        chunks.append("| City | Fetched | Rented | Price changes |\n")
        chunks.append("|------|---------|--------|---------------|\n")
        for r in buy_rows:
            chunks.append(f"| {r['city']} | {r['fetched']} | {r.get('rented', 0)} | {r['price_changes']} |\n")
        chunks.append("|------|---------|--------|---------------|\n")
        chunks.append(f"| **Total** | **{total_fetched}** | **{total_rented}** | **{total_changes}** |\n\n")

    rent_rows = _merge_by_city(r for r in all_rows if r.get("type") == "rent")
    if rent_rows:
        total_fetched = sum(r["fetched"] for r in rent_rows)
        total_changes = sum(r["price_changes"] for r in rent_rows)
        chunks.append("### 🔑 Rent\n\n")
        chunks.append("| City | Fetched | Price changes |\n")
        chunks.append("|------|--------:|--------------:|\n")
        for r in rent_rows:
            chunks.append(f"| {r['city']} | {r['fetched']} | {r['price_changes']} |\n")
        chunks.append("|------|---------|---------------|\n")
        chunks.append(f"| **Total** | **{total_fetched}** | **{total_changes}** |\n\n")

    contract_rows = [r for r in all_rows if r.get("type") == "contracts"]
    if contract_rows:
        chunks.append("### 📋 Contract Details\n\n")
        chunks.append("| City | Processed | Extracted | With Rent | With Expiry |\n")
        chunks.append("|------|----------:|----------:|----------:|------------:|\n")
        for r in contract_rows:
            chunks.append(
                f"| {r['city']} | {r['processed']} | {r.get('extracted', 0)} "
                f"| {r.get('with_rent', 0)} | {r.get('with_expiry', 0)} |\n"
            )
        t_proc = sum(r["processed"] for r in contract_rows)
        t_ext = sum(r.get("extracted", 0) for r in contract_rows)
        t_rent = sum(r.get("with_rent", 0) for r in contract_rows)
        t_exp = sum(r.get("with_expiry", 0) for r in contract_rows)
        chunks.append("|------|----------|----------|----------|------------|\n")
        chunks.append(f"| **Total** | **{t_proc}** | **{t_ext}** | **{t_rent}** | **{t_exp}** |\n\n")

    est_rows = [r for r in all_rows if r.get("type") == "estimates"]
    if est_rows:
        chunks.append("### 📊 Rent Estimates\n\n")
        chunks.append("| City | Estimates updated |\n")
        chunks.append("|------|------------------:|\n")
        for r in est_rows:
            chunks.append(f"| {r['city']} | {r.get('computed', 0)} |\n")
        total_est = sum(r.get("computed", 0) for r in est_rows)
        chunks.append("|------|-------------------|\n")
        chunks.append(f"| **Total** | **{total_est}** |\n\n")

    cluster_rows = [r for r in all_rows if r.get("type") == "clusters"]
    if cluster_rows:
        chunks.append("### 🔗 Multi-Agency Clusters\n\n")
        chunks.append("| City | Listings | Multi-Agency Clusters | Duplicate Ads |\n")
        chunks.append("|------|---------:|----------------------:|--------------:|\n")
        for r in cluster_rows:
            chunks.append(
                f"| {r['city']} | {r.get('listings', 0)} "
                f"| {r.get('multi_agency_clusters', 0)} | {r.get('duplicate_listings', 0)} |\n"
            )

    alert_rows = [r for r in all_rows if r.get("type") == "alerts"]
    if alert_rows:
        chunks.append("### 🔔 Deal Alerts\n\n")
        chunks.append("| Searches Matched | Searches Notified | Listings Matched | Sent |\n")
        chunks.append("|-----------------:|------------------:|-----------------:|-----:|\n")
        for r in alert_rows:
            chunks.append(
                f"| {r.get('searches_matched', 0)} | {r.get('searches_notified', 0)} "
                f"| {r.get('listings_matched', 0)} | {r.get('notifications_sent', 0)} |\n"
            )

    return "".join(chunks)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    stats_dir = pathlib.Path(args[0]) if args else pathlib.Path("stats")
    summary = render_job_summary(stats_dir)
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        pathlib.Path(out).write_text(summary, encoding="utf-8")
    else:
        sys.stdout.write(summary)


if __name__ == "__main__":
    main()
