# Shared retail anomaly detection pipeline (CLI, web, tests).

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

# Repo root; default simulator CSV and output folder for raw exports.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "retail_data_quality_sim.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"

# For inferring YYYY-MM-DD from free text (e.g. chat messages).
_ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


# First YYYY-MM-DD substring in text, or None.
def extract_iso_date_from_text(text: str) -> str | None:
    m = _ISO_DATE.search(text or "")
    return m.group(1) if m else None


# Analysis day: explicit as_of_date, else ISO date in user_message, else max metric date in CSV.
def resolve_as_of_timestamp(
    full_df: pd.DataFrame,
    as_of_date: str | None,
    user_message: str = "",
) -> pd.Timestamp:
    if as_of_date is not None and str(as_of_date).strip():
        return pd.Timestamp(str(as_of_date).strip()).normalize()
    inferred = extract_iso_date_from_text(user_message)
    if inferred:
        return pd.Timestamp(inferred).normalize()
    d_max = full_df[COL_DATE].max()
    if pd.isna(d_max):
        raise ValueError("No valid metric dates in the metrics CSV.")
    return d_max.normalize()


# Rows where metricdate is in [end - days, end], inclusive.
def filter_history_window(
    df: pd.DataFrame, end: pd.Timestamp, days: int
) -> pd.DataFrame:
    end_ts = end.normalize()
    start_ts = end_ts - timedelta(days=days)
    return df[(df["metricdate"] >= start_ts) & (df["metricdate"] <= end_ts)]


# Keep top n anomalies per (storeid, deptname) by impact_score; n<=0 or None means all.
def apply_top_n_per_store_dept(
    anomalies: list[dict],
    n: int | None,
) -> list[dict]:
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


# Write raw_anomalies_<date>.json and .csv under output_dir (default OUTPUT_DIR).
def save_raw_anomalies(
    anomalies: list[dict],
    date_label: str,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    root = output_dir if output_dir is not None else OUTPUT_DIR
    root.mkdir(parents=True, exist_ok=True)
    stem = f"raw_anomalies_{date_label}"
    json_path = root / f"{stem}.json"
    csv_path = root / f"{stem}.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(anomalies, f, indent=2, ensure_ascii=False, default=str)

    pd.DataFrame(anomalies).to_csv(csv_path, index=False)

    return json_path, csv_path


# Full user message for the LLM: date + instructions + formatted anomaly block.
def build_user_prompt(as_of: str, anomaly_block: str) -> str:
    return (
        f"Daily retail data quality review for {as_of}.\n\n"
        "Structured anomaly input follows. Severities, impact scores, and business "
        "hints are **already computed**—explain them; do not replace them with your "
        "own guesses.\n\n"
        f"{anomaly_block}"
    )


# Return value of run_detection_pipeline.
@dataclass(frozen=True)
class PipelineResult:
    # All enriched anomalies (same list saved when save_exports is True).
    anomalies: list[dict]
    # After optional top-n per store/dept cap, for LLM formatting.
    anomalies_for_llm: list[dict]
    # Human + machine-readable anomaly text from format_anomalies_for_llm.
    formatted_anomaly_block: str
    # build_user_prompt(as_of_str, formatted_anomaly_block).
    formatted_prompt: str
    # Resolved analysis timestamp (normalized).
    as_of: pd.Timestamp
    # as_of as YYYY-MM-DD.
    as_of_str: str


def run_detection_pipeline_from_dataframe(
    metrics_df: pd.DataFrame,
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
    """Run detectors on an in-memory metrics DataFrame (orchestration / data sources)."""
    return _run_pipeline_core(
        metrics_df,
        as_of_date=as_of_date,
        user_message=user_message,
        history_days=history_days,
        z_threshold=z_threshold,
        grain_min_distinct_days=grain_min_distinct_days,
        grain_min_avg=grain_min_avg,
        top_n=top_n,
        save_exports=save_exports,
        output_dir=output_dir,
    )


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
    # Load CSV, run all detectors, enrich, optional exports, build LLM prompt (run_day / ADK path).
    # as_of_date or first ISO date in user_message or latest metricdate; history_days ends on as-of.
    # top_n caps per (store, dept) before format_anomalies_for_llm; grain_* tune inconsistent-grain rule.
    path = Path(csv_path)
    full = load_metrics(str(path))
    return _run_pipeline_core(
        full,
        as_of_date=as_of_date,
        user_message=user_message,
        history_days=history_days,
        z_threshold=z_threshold,
        grain_min_distinct_days=grain_min_distinct_days,
        grain_min_avg=grain_min_avg,
        top_n=top_n,
        save_exports=save_exports,
        output_dir=output_dir,
    )


def _run_pipeline_core(
    full: pd.DataFrame,
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
    as_of_ts = resolve_as_of_timestamp(full, as_of_date, user_message)
    as_of_str = as_of_ts.strftime("%Y-%m-%d")

    if COL_DATE in full.columns and not full[COL_DATE].is_monotonic_increasing:
        full = full.sort_values(COL_DATE, kind="mergesort")

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
