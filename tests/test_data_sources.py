"""Data source factory and providers."""

from __future__ import annotations

import pandas as pd
import pytest

from config.settings import Settings
from myagent.data_sources.base import DataSourceConfigurationError
from myagent.data_sources.factory import get_metrics_data_source
from myagent.data_sources.local_csv import LocalCsvMetricsSource


def test_factory_defaults_to_local_csv():
    s = Settings(retail_data_source="local_csv")
    provider = get_metrics_data_source(s)
    assert isinstance(provider, LocalCsvMetricsSource)
    assert provider.name == "local_csv"


def test_local_csv_loads_sample_file(sample_csv_path):
    s = Settings(retail_data_source="local_csv", retail_metrics_csv=sample_csv_path)
    df = get_metrics_data_source(s).fetch_metrics()
    assert isinstance(df, pd.DataFrame)
    assert "metricdate" in df.columns
    assert len(df) > 0


def test_databricks_missing_config_raises():
    s = Settings(retail_data_source="databricks_mcp")
    provider = get_metrics_data_source(s)
    with pytest.raises(DataSourceConfigurationError) as exc:
        provider.fetch_metrics()
    assert "DATABRICKS_MCP_SERVER_URL" in str(exc.value)


def test_databricks_configured_raises_not_implemented():
    s = Settings(
        retail_data_source="databricks_mcp",
        databricks_mcp_server_url="https://example.invalid/mcp",
        databricks_metrics_catalog="cat",
        databricks_metrics_schema="schema",
        databricks_metrics_table="metrics",
    )
    provider = get_metrics_data_source(s)
    with pytest.raises(NotImplementedError):
        provider.fetch_metrics()


def test_unknown_source_raises():
    s = Settings()
    with pytest.raises(ValueError, match="Unknown data source"):
        get_metrics_data_source(s, source="warehouse_x")
