# ADK tool: run live anomaly detection for the web chatbot.

from __future__ import annotations

from dotenv import load_dotenv

from config.settings import get_settings
from myagent.pipeline import DEFAULT_CSV, run_detection_pipeline


# Run detection pipeline from settings (CSV path, thresholds); save raw exports; return formatted_prompt for the model.
# as_of_date or ISO date in user_message or latest CSV date. Same prompt shape as run_day.py.
def run_retail_data_quality_analysis(
    user_message: str = "",
    as_of_date: str | None = None,
) -> str:
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
