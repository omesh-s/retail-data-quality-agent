"""Shared pipeline orchestration and provider resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from config.settings import Settings
from myagent.anomaly_detector import normalize_metrics_dataframe
from myagent.data_sources.local_csv import LocalCsvMetricsSource
from myagent.orchestration.pipeline_run import (
    resolve_metrics_provider,
    run_anomaly_pipeline,
)


def test_csv_path_override_forces_local_csv(sample_csv_path):
    s = Settings(retail_data_source="databricks_mcp")
    provider = resolve_metrics_provider(s, csv_path=sample_csv_path)
    assert isinstance(provider, LocalCsvMetricsSource)


@patch("myagent.orchestration.pipeline_run.get_metrics_data_source")
def test_run_anomaly_pipeline_uses_provider(mock_get_source, sample_csv_path):
    mock_df = pd.read_csv(sample_csv_path)
    mock_df = normalize_metrics_dataframe(mock_df)
    provider = MagicMock()
    provider.name = "local_csv"
    provider.fetch_metrics.return_value = mock_df
    mock_get_source.return_value = provider

    s = Settings(retail_history_days=30)
    result = run_anomaly_pipeline(
        as_of_date="2024-05-20",
        settings=s,
        save_exports=False,
    )
    assert result.data_source == "local_csv"
    assert result.pipeline.as_of_str == "2024-05-20"
    assert len(result.pipeline.anomalies) >= 0


def test_normalize_metrics_dataframe_aliases():
    raw = pd.DataFrame(
        {
            "dept_name": ["Dairy"],
            "metric_code": ["UNITS_SOLD"],
            "store_id": [1],
            "metric_date": ["2024-05-20"],
            "metric_value": [10.0],
        }
    )
    out = normalize_metrics_dataframe(raw)
    assert list(out.columns) == [
        "Deptname",
        "metriccode",
        "Storeid",
        "metricdate",
        "metricvalue",
    ]
