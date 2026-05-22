"""Databricks MCP client and provider (mocked HTTP)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from config.settings import Settings
from myagent.data_sources.databricks_mcp import DatabricksMcpMetricsSource
from myagent.integrations.databricks_mcp_client import (
    DatabricksMcpClient,
    DatabricksMcpClientError,
)


def _settings(**kwargs) -> Settings:
    base = dict(
        retail_data_source="databricks_mcp",
        databricks_mcp_server_url="https://mcp.example.invalid/rpc",
        databricks_metrics_catalog="retail",
        databricks_metrics_schema="metrics",
        databricks_metrics_table="daily_store",
        databricks_mcp_tool_name="execute_sql",
    )
    base.update(kwargs)
    return Settings(**base)


def test_mcp_client_parses_json_rows_in_content():
    rows = [
        {
            "dept_name": "Dairy",
            "metric_code": "UNITS_SOLD",
            "store_id": 1,
            "metric_date": "2024-05-20",
            "metric_value": 5.0,
        }
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {
            "content": [{"type": "text", "text": json.dumps(rows)}],
        }
    }
    session = MagicMock()
    session.post.return_value = mock_resp

    client = DatabricksMcpClient(_settings(), session=session)
    df = client.execute_sql("SELECT 1")
    assert len(df) == 1
    assert "dept_name" in df.columns or "Deptname" in df.columns


def test_mcp_client_sends_auth_header():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": {"content": [{"type": "text", "text": "[]"}]}}
    session = MagicMock()
    session.post.return_value = mock_resp

    client = DatabricksMcpClient(
        _settings(databricks_mcp_auth_token="secret-token"), session=session
    )
    client.execute_sql("SELECT 1")
    call_kwargs = session.post.call_args.kwargs
    headers = call_kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer secret-token"


def test_mcp_client_parses_csv_text_in_content():
    csv_text = "dept_name,metric_code,store_id,metric_date,metric_value\nDairy,CUST_COUNT,1,2024-05-20,1.0\n"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {"content": [{"type": "text", "text": csv_text}]}
    }
    session = MagicMock()
    session.post.return_value = mock_resp

    client = DatabricksMcpClient(_settings(), session=session)
    df = client.execute_sql("SELECT 1")
    assert len(df) == 1


def test_mcp_client_http_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "server error"
    session = MagicMock()
    session.post.return_value = mock_resp

    client = DatabricksMcpClient(_settings(), session=session)
    with pytest.raises(DatabricksMcpClientError, match="HTTP 500"):
        client.execute_sql("SELECT 1")


@patch("myagent.data_sources.databricks_mcp.DatabricksMcpClient")
def test_databricks_provider_normalizes(mock_client_cls):
    raw = pd.DataFrame(
        {
            "dept_name": ["Meat"],
            "metric_code": ["REVENUE_USD"],
            "store_id": [2],
            "metric_date": ["2024-05-20"],
            "metric_value": [100.0],
        }
    )
    mock_client_cls.return_value.execute_sql.return_value = raw

    provider = DatabricksMcpMetricsSource(_settings(), client=mock_client_cls.return_value)
    df = provider.fetch_metrics()
    assert "Deptname" in df.columns
    assert "metricdate" in df.columns
    mock_client_cls.return_value.execute_sql.assert_called_once()
    sql = mock_client_cls.return_value.execute_sql.call_args[0][0]
    assert "retail" in sql and "daily_store" in sql


def test_databricks_custom_sql_setting():
    s = _settings(databricks_metrics_sql="SELECT dept_name FROM t LIMIT 1")
    provider = DatabricksMcpMetricsSource(s, client=MagicMock())
    assert provider._build_sql() == "SELECT dept_name FROM t LIMIT 1"
