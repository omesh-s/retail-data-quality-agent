"""ADK tool: run live anomaly detection for the web chatbot."""

from __future__ import annotations

from dotenv import load_dotenv

from config.settings import get_settings
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

    Configuration:
        See ``config/settings.py`` / ``.env.example`` (``RETAIL_*`` variables).
    """
    load_dotenv()
    s = get_settings()
    csv_path = s.retail_metrics_csv or DEFAULT_CSV

    result = run_detection_pipeline(
        csv_path,
        as_of_date=as_of_date if as_of_date and str(as_of_date).strip() else None,
        user_message=user_message or "",
        history_days=s.retail_history_days,
        z_threshold=s.retail_z_threshold,
        grain_min_distinct_days=s.retail_grain_min_distinct,
        grain_min_avg=s.retail_grain_min_avg,
        top_n=s.retail_top_n,
        save_exports=True,
    )
    return result.formatted_prompt
