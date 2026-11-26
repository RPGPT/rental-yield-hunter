"""Tests for stdlib-only CI summary rendering and lazy pipeline package exports."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

import yieldhunter.pipeline as pipeline
from yieldhunter.pipeline.stats import render_job_summary

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_stats_module_runs_with_stdlib_only(tmp_path: pathlib.Path) -> None:
    """CI's summarise job runs ``python3 -m yieldhunter.pipeline.stats`` without deps."""
    stats_dir = tmp_path / "stats"
    stats_dir.mkdir()
    (stats_dir / "stats-buy-lisboa-imovirtual.json").write_text(
        json.dumps({"type": "buy", "city": "Lisboa", "fetched": 10, "rented": 2, "price_changes": 1}),
        encoding="utf-8",
    )
    (stats_dir / "stats-buy-lisboa-era.json").write_text(
        json.dumps({"type": "buy", "city": "Lisboa", "fetched": 5, "rented": 1, "price_changes": 0}),
        encoding="utf-8",
    )
    (stats_dir / "stats-rent-porto-imovirtual.json").write_text(
        json.dumps({"type": "rent", "city": "Porto", "fetched": 8, "price_changes": 2}),
        encoding="utf-8",
    )
    (stats_dir / "stats-contracts-lisboa.json").write_text(
        json.dumps(
            {"type": "contracts", "city": "Lisboa", "processed": 4, "extracted": 3, "with_rent": 2, "with_expiry": 1}
        ),
        encoding="utf-8",
    )
    (stats_dir / "stats-estimates-lisboa.json").write_text(
        json.dumps({"type": "estimates", "city": "Lisboa", "computed": 12}),
        encoding="utf-8",
    )
    (stats_dir / "stats-clusters-all.json").write_text(
        json.dumps(
            {"type": "clusters", "city": None, "listings": 100, "multi_agency_clusters": 5, "duplicate_listings": 12}
        ),
        encoding="utf-8",
    )
    (stats_dir / "stats-alerts.json").write_text(
        json.dumps(
            {
                "type": "alerts",
                "searches_matched": 2,
                "searches_notified": 1,
                "listings_matched": 3,
                "notifications_sent": 1,
            }
        ),
        encoding="utf-8",
    )

    summary_file = tmp_path / "step_summary.md"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "GITHUB_STEP_SUMMARY": str(summary_file),
    }

    # -S omits site-packages so any third-party import fails just like on the bare CI runner.
    proc = subprocess.run(
        [sys.executable, "-S", "-m", "yieldhunter.pipeline.stats", str(stats_dir)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    assert proc.stderr == ""

    summary = summary_file.read_text(encoding="utf-8")
    assert "## 🏠 Scrape Summary" in summary
    assert "| Lisboa | 15 | 3 | 1 |" in summary
    assert "| Porto | 8 | 2 |" in summary
    assert "### 📋 Contract Details" in summary
    assert "### 📊 Rent Estimates" in summary
    assert "### 🔗 Multi-Agency Clusters" in summary
    assert "### 🔔 Deal Alerts" in summary


def test_render_job_summary_missing_or_empty_dir(tmp_path: pathlib.Path) -> None:
    assert "No stats available" in render_job_summary(tmp_path / "does-not-exist")
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert "No stats available" in render_job_summary(empty_dir)


def test_pipeline_lazy_exports() -> None:
    for name in pipeline.__all__:
        assert callable(getattr(pipeline, name))

    with pytest.raises(AttributeError):
        getattr(pipeline, "non_existent_pipeline_export")
