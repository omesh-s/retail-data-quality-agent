"""Shared retail anomaly detection pipeline (CLI, web, tests)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from myagent.anomaly_detector import (
    COL_DATE,
    find_inconsistent_grain,
    find_missing_systemon_streaks,
    find_negative_outliers,
    find_positive_spikes,
    load_metrics,
)
from myagent.anomaly_impact import enrich_anomalies
from myagent.anomaly_to_prompt import format_anomalies_for_llm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "retail_data_quality_sim.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"

_ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def extract_iso_date_from_text(text: str) -> str | None:
    """Return the first YYYY-MM-DD substring in *text*, if any."""
    m = _ISO_DATE.search(text or "")
    return m.group(1) if m else None


def resolve_as_of_timestamp(
    full_df: pd.DataFrame,
    as_of_date: str | None,
    user_message: str = "",
) -> pd.Timestamp:
    """Pick the analysis day: explicit arg, then ISO date in text, else max CSV date."""
    if as_of_date is not None and str(as_of_date).strip():
        return pd.Timestamp(str(as_of_date).strip()).normalize()
    inferred = extract_iso_date_from_text(user_message)
    if inferred:
        return pd.Timestamp(inferred).normalize()
    d_max = full_df[COL_DATE].max()
    if pd.isna(d_max):
        raise ValueError("No valid metric dates in the metrics CSV.")
    return d_max.normalize()


def filter_history_window(
    df: pd.DataFrame, end: pd.Timestamp, days: int
) -> pd.DataFrame:
    """Keep rows with metricdate in [end - days, end] inclusive."""
    end_ts = end.normalize()
    start_ts = end_ts - timedelta(days=days)
    return df[(df["metricdate"] >= start_ts) & (df["metricdate"] <= end_ts)]


def apply_top_n_per_store_dept(
    anomalies: list[dict],
    n: int | None,
) -> list[dict]:
    """Keep the top *n* anomalies per (storeid, deptname) by ``impact_score``."""
    if n is None or n <= 0:
        return anomalies
    buckets: dict[tuple[Any, Any], list[dict]] = defaultdict(list)
    for rec in anomalies:
        buckets[(rec.get("storeid"), rec.get("deptname"))].append(rec)
    out: list[dict] = []
    for _key, items in buckets.items():
        ranked = sorted(
            items,
            key=lambda r: -float(r.get("impact_score") or 0.0),
        )
        out.extend(ranked[:n])
    out.sort(
        key=lambda r: (
            {"High": 0, "Medium": 1, "Low": 2}.get(str(r.get("severity")), 2),
            str(r.get("storeid")),
            str(r.get("deptname")),
        )
    )
    return out


def save_raw_anomalies(
    anomalies: list[dict],
    date_label: str,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Write ``raw_anomalies_<date>.json`` and ``.csv`` under *output_dir*."""
    root = output_dir if output_dir is not None else OUTPUT_DIR
    root.mkdir(parents=True, exist_ok=True)
    stem = f"raw_anomalies_{date_label}"
    json_path = root / f"{stem}.json"
    csv_path = root / f"{stem}.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(anomalies, f, indent=2, ensure_ascii=False, default=str)

    pd.DataFrame(anomalies).to_csv(csv_path, index=False)

    return json_path, csv_path


def build_user_prompt(as_of: str, anomaly_block: str) -> str:
    """Wrap formatted anomalies for the LLM (same text as ``run_day``)."""
    return (
        f"Daily retail data quality review for {as_of}.\n\n"
        "Structured anomaly input follows. Severities, impact scores, and business "
        "hints are **already computed**—explain them; do not replace them with your "
        "own guesses.\n\n"
        f"{anomaly_block}"
    )


@dataclass(frozen=True)
class PipelineResult:
    """Outputs of :func:`run_detection_pipeline`."""

    anomalies: list[dict]
    """Full enriched list (same as written to ``output/``)."""
    anomalies_for_llm: list[dict]
    """Subset after optional per store/dept top-*n* cap."""
    formatted_anomaly_block: str
    """Output of :func:`format_anomalies_for_llm` on ``anomalies_for_llm``."""
    formatted_prompt: str
    """Full user message: :func:`build_user_prompt` + ``formatted_anomaly_block``."""
    as_of: pd.Timestamp
    as_of_str: str


def run_detection_pipeline(
    csv_path: str | Path,
    *,
    as_of_date: str | None = None,
    user_message: str = "",
    history_days: int = 30,
    z_threshold: float = 4.0,
    grain_min_distinct_days: int = 3,
    grain_min_avg: float | None = None,
    top_n: int | None = None,
    save_exports: bool = True,
    output_dir: str | Path | None = None,
) -> PipelineResult:
    """Run detectors, enrich, optionally save exports, build prompt text.

    Detection and enrichment logic matches ``run_day.py`` / ``evaluate.py``.

    Args:
        csv_path: Retail metrics CSV path.
        as_of_date: Optional ``YYYY-MM-DD``. If unset, uses first ISO date in
            ``user_message``, else the latest ``metricdate`` in the file.
        user_message: Free text (e.g. user chat) for date inference.
        history_days: Window length ending on the as-of day.
        z_threshold: Positive spike z-score threshold.
        grain_min_distinct_days: Inconsistent grain lookback distinct-day minimum.
        grain_min_avg: Optional minimum mean metric value for grain signals.
        top_n: Cap anomalies per (store, dept) before formatting (``None`` = all).
        save_exports: If True, write JSON/CSV under ``output_dir``.
        output_dir: Override default ``output/`` project folder.

    Returns:
        :class:`PipelineResult` with enriched rows and prompt strings.
    """
    path = Path(csv_path)
    full = load_metrics(str(path))
    as_of_ts = resolve_as_of_timestamp(full, as_of_date, user_message)
    as_of_str = as_of_ts.strftime("%Y-%m-%d")

    window_df = filter_history_window(full, as_of_ts, history_days)

    anomalies: list[dict] = []
    anomalies.extend(find_negative_outliers(window_df))
    anomalies.extend(find_positive_spikes(window_df, z_threshold=z_threshold))
    anomalies.extend(find_missing_systemon_streaks(window_df, window_days=7))
    anomalies.extend(
        find_inconsistent_grain(
            window_df,
            lookback_days=7,
            as_of=as_of_ts,
            min_distinct_days=grain_min_distinct_days,
            min_avg_value=grain_min_avg,
        )
    )

    anomalies = enrich_anomalies(window_df, anomalies, as_of=as_of_ts)

    out_dir = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    if save_exports:
        save_raw_anomalies(anomalies, as_of_str, out_dir)

    for_llm = apply_top_n_per_store_dept(anomalies, top_n)
    formatted_block = format_anomalies_for_llm(for_llm)
    prompt = build_user_prompt(as_of_str, formatted_block)

    return PipelineResult(
        anomalies=anomalies,
        anomalies_for_llm=for_llm,
        formatted_anomaly_block=formatted_block,
        formatted_prompt=prompt,
        as_of=as_of_ts,
        as_of_str=as_of_str,
    )
