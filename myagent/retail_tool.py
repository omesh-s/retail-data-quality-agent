"""ADK tool: run live anomaly detection for the web chatbot."""

from __future__ import annotations

from dotenv import load_dotenv

from config.settings import get_settings
from myagent.orchestration.pipeline_run import run_anomaly_pipeline


def run_retail_data_quality_analysis(
    user_message: str = "",
    as_of_date: str | None = None,
) -> str:
    """Run the real retail metrics pipeline and return structured facts for summarization.

    **Call this tool for every request** about data quality, anomalies, or a specific
    day's metrics—before answering. The return value is the only authoritative anomaly
    list (with severities and impact fields). Do not invent anomalies.

    Resolves metrics through the configured data source (``RETAIL_DATA_SOURCE``),
    runs deterministic detectors, enriches records, writes
    ``output/raw_anomalies_<date>.json`` and ``.csv``, and returns the same prompt
    block used by ``run_day.py``.

    Args:
        user_message: The user's message (used to find ``YYYY-MM-DD`` if ``as_of_date``
            is omitted).
        as_of_date: Calendar day ``YYYY-MM-DD``. If omitted and no ISO date appears
            in ``user_message``, the latest ``metricdate`` in the data is used.

    Returns:
        Full formatted user prompt (date line + structured anomaly sections) to ground
        the model reply.
    """
    load_dotenv()
    s = get_settings()

    result = run_anomaly_pipeline(
        as_of_date=as_of_date if as_of_date and str(as_of_date).strip() else None,
        user_message=user_message or "",
        settings=s,
        save_exports=True,
    )
    return result.pipeline.formatted_prompt
