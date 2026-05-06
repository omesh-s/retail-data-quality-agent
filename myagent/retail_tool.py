"""ADK tool: run live anomaly detection for the web chatbot."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from myagent.pipeline import DEFAULT_CSV, run_detection_pipeline


def run_retail_data_quality_analysis(
    user_message: str = "",
    as_of_date: str | None = None,
) -> str:
    """Run the real retail metrics pipeline and return structured facts for summarization.

    **Call this tool for every request** about data quality, anomalies, or a specific
    day's metrics—before answering. The return value is the only authoritative anomaly
    list (with severities and impact fields). Do not invent anomalies.

    The pipeline loads the metrics CSV, runs deterministic detectors, enriches
    records, writes ``output/raw_anomalies_<date>.json`` and ``.csv``, and returns
    the same prompt block used by ``run_day.py``.

    Args:
        user_message: The user's message (used to find ``YYYY-MM-DD`` if ``as_of_date``
            is omitted).
        as_of_date: Calendar day ``YYYY-MM-DD``. If omitted and no ISO date appears
            in ``user_message``, the latest ``metricdate`` in the CSV is used.

    Returns:
        Full formatted user prompt (date line + structured anomaly sections) to ground
        the model reply.

    Environment (optional):
        ``RETAIL_METRICS_CSV``: path to CSV (default: project ``data/retail_data_quality_sim.csv``).
        ``RETAIL_HISTORY_DAYS``, ``RETAIL_Z_THRESHOLD``, ``RETAIL_GRAIN_MIN_DISTINCT``,
        ``RETAIL_GRAIN_MIN_AVG``, ``RETAIL_TOP_N``: override pipeline defaults for the web UI.
    """
    load_dotenv()

    csv_raw = os.environ.get("RETAIL_METRICS_CSV", "").strip()
    csv_path = Path(csv_raw) if csv_raw else DEFAULT_CSV

    def _int_env(name: str, default: int) -> int:
        v = os.environ.get(name, "").strip()
        return int(v) if v else default

    def _float_env(name: str, default: float) -> float:
        v = os.environ.get(name, "").strip()
        return float(v) if v else default

    def _opt_float(name: str) -> float | None:
        v = os.environ.get(name, "").strip()
        return float(v) if v else None

    def _opt_int(name: str) -> int | None:
        v = os.environ.get(name, "").strip()
        return int(v) if v else None

    history_days = _int_env("RETAIL_HISTORY_DAYS", 30)
    z_threshold = _float_env("RETAIL_Z_THRESHOLD", 4.0)
    grain_distinct = _int_env("RETAIL_GRAIN_MIN_DISTINCT", 3)
    grain_min_avg = _opt_float("RETAIL_GRAIN_MIN_AVG")
    top_n = _opt_int("RETAIL_TOP_N")

    result = run_detection_pipeline(
        csv_path,
        as_of_date=as_of_date if as_of_date and str(as_of_date).strip() else None,
        user_message=user_message or "",
        history_days=history_days,
        z_threshold=z_threshold,
        grain_min_distinct_days=grain_distinct,
        grain_min_avg=grain_min_avg,
        top_n=top_n,
        save_exports=True,
    )
    return result.formatted_prompt
