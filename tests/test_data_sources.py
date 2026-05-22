"""Data source factory and providers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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


@patch("myagent.integrations.databricks_mcp_client.requests.Session.post")
def test_databricks_provider_calls_mcp(mock_post):
    rows = [
        {
            "dept_name": "Dairy",
            "metric_code": "CUST_COUNT",
            "store_id": 1,
            "metric_date": "2024-05-20",
            "metric_value": 1.0,
        }
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {"content": [{"type": "text", "text": __import__("json").dumps(rows)}]}
    }
    mock_post.return_value = mock_resp

    s = Settings(
        retail_data_source="databricks_mcp",
        databricks_mcp_server_url="https://example.invalid/mcp",
        databricks_metrics_catalog="cat",
        databricks_metrics_schema="schema",
        databricks_metrics_table="metrics",
    )
    df = get_metrics_data_source(s).fetch_metrics()
    assert "Deptname" in df.columns
    assert len(df) == 1


def test_unknown_source_raises():
    s = Settings()
    with pytest.raises(ValueError, match="Unknown data source"):
        get_metrics_data_source(s, source="warehouse_x")
