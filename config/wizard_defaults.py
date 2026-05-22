"""Sensible defaults applied when advanced setup is skipped."""

from __future__ import annotations

PIPELINE_ADVANCED_DEFAULTS: dict[str, str] = {
    "RETAIL_HISTORY_DAYS": "30",
    "RETAIL_Z_THRESHOLD": "4.0",
    "RETAIL_GRAIN_MIN_DISTINCT": "3",
    "DAILY_REPORT_TOP_N": "10",
}

# Keys intentionally left unset (blank) unless user configures advanced section.
PIPELINE_ADVANCED_OPTIONAL_KEYS: tuple[str, ...] = (
    "RETAIL_GRAIN_MIN_AVG",
    "RETAIL_TOP_N",
)

SAMPLE_CSV_RELATIVE = "data/retail_data_quality_sim.csv"
