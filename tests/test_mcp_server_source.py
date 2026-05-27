"""Tests for the mcp_server data source mode."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from config.settings import Settings
from myagent.integrations.mcp_stdio_client import McpToolResult
from myagent.orchestration.pipeline_run import (
    AnomalyPipelineRunResult,
    _map_mcp_anomaly,
    run_anomaly_pipeline,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_MCP_RESPONSE = {
    "check_date": "2024-05-20",
    "window_start": "2024-05-06",
    "lookback_days": 14,
    "dept_filter": "all",
    "total_anomalies": 2,
    "wfm_required_count": 1,
    "anomalies_by_rule": {"continuity_gap": 1, "positive_spike": 1},
    "summary": "Found 2 anomalies.",
    "anomaly_list": [
        {
            "issue_type": "Positive Spike",
            "dept_desc": "Market",
            "metric_cd": "MKT_FRSH_UN",
            "store_id": 42,
            "sub_dept": None,
            "check_date": "2024-05-20",
            "metric_value": 999.99,
            "historical_mean": 100.0,
            "historical_std": 10.0,
            "z_score": 89.99,
            "severity": "High",
            "is_wfm_required": True,
            "details": "Value 999.99 is 90.0 std-devs above historical mean 100.00.",
        },
        {
            "issue_type": "Continuity Gap",
            "dept_desc": "Bakery",
            "metric_cd": "BKY_3A_UN",
            "store_id": 7,
            "sub_dept": "3A",
            "check_date": "2024-05-20",
            "consecutive_missing_days": 10,
            "last_missing_date": "2024-05-19",
            "severity": "Medium",
            "is_wfm_required": False,
            "details": "Metric absent for 10 consecutive days.",
        },
    ],
}


@pytest.fixture()
def mcp_settings(tmp_path):
    fake_script = tmp_path / "server.py"
    fake_script.write_text("# stub")
    return Settings(
        retail_data_source="mcp_server",
        wfm_dq_mcp_server_path=str(fake_script),
        llm_provider="googlegenai",
        google_api_key="test-key",
        daily_report_default_send_slack=False,
    )


def _mock_result(data: dict | None = None) -> McpToolResult:
    return McpToolResult(
        content_text=json.dumps(data or _SAMPLE_MCP_RESPONSE),
        is_error=False,
    )


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


class TestMapMcpAnomaly:
    def test_high_severity_spike(self):
        raw = _SAMPLE_MCP_RESPONSE["anomaly_list"][0]
        mapped = _map_mcp_anomaly(raw)

        assert mapped["storeid"] == 42
        assert mapped["deptname"] == "Market"
        assert mapped["metriccode"] == "MKT_FRSH_UN"
        assert mapped["metricvalue"] == 999.99
        assert mapped["date_or_range"] == "2024-05-20"
        assert mapped["issue_type"] == "Positive Spike"
        assert mapped["severity"] == "High"
        assert mapped["impact_score"] == 0.85
        assert mapped["details"].startswith("Value 999.99")
        assert mapped["is_wfm_required"] is True
        assert mapped["customer_impact"] == "High"
        assert mapped["operational_risk"] == "High"

    def test_medium_severity_gap(self):
        raw = _SAMPLE_MCP_RESPONSE["anomaly_list"][1]
        mapped = _map_mcp_anomaly(raw)

        assert mapped["severity"] == "Medium"
        assert mapped["impact_score"] == 0.50
        assert mapped["storeid"] == 7
        assert mapped["deptname"] == "Bakery"
        assert mapped["customer_impact"] == "Medium"

    def test_low_severity_defaults(self):
        mapped = _map_mcp_anomaly({"severity": "Low", "details": "minor"})
        assert mapped["impact_score"] == 0.20
        assert mapped["customer_impact"] is None
        assert mapped["operational_risk"] is None


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


class TestMcpServerPipeline:
    @patch("myagent.orchestration.pipeline_run.call_mcp_tool")
    def test_returns_pipeline_result(self, mock_call, mcp_settings, tmp_path):
        mock_call.return_value = _mock_result()

        result = run_anomaly_pipeline(
            as_of_date="2024-05-20",
            settings=mcp_settings,
            save_exports=True,
            output_dir=str(tmp_path),
        )

        assert isinstance(result, AnomalyPipelineRunResult)
        assert result.data_source == "mcp_server"
        assert len(result.pipeline.anomalies) == 2
        assert result.pipeline.as_of_str == "2024-05-20"
        assert "Store" in result.pipeline.formatted_anomaly_block

    @patch("myagent.orchestration.pipeline_run.call_mcp_tool")
    def test_exports_json_and_csv(self, mock_call, mcp_settings, tmp_path):
        mock_call.return_value = _mock_result()

        run_anomaly_pipeline(
            as_of_date="2024-05-20",
            settings=mcp_settings,
            save_exports=True,
            output_dir=str(tmp_path),
        )

        assert (tmp_path / "raw_anomalies_2024-05-20.json").exists()
        assert (tmp_path / "raw_anomalies_2024-05-20.csv").exists()

    @patch("myagent.orchestration.pipeline_run.call_mcp_tool")
    def test_passes_check_date_and_lookback(self, mock_call, mcp_settings):
        mock_call.return_value = _mock_result()

        run_anomaly_pipeline(
            as_of_date="2024-05-20",
            history_days=7,
            settings=mcp_settings,
            save_exports=False,
        )

        _, kwargs = mock_call.call_args
        assert kwargs["arguments"]["check_date"] == "2024-05-20"
        assert kwargs["arguments"]["lookback_days"] == 7

    @patch("myagent.orchestration.pipeline_run.call_mcp_tool")
    def test_skips_local_detection(self, mock_call, mcp_settings, tmp_path):
        mock_call.return_value = _mock_result()

        with patch("myagent.pipeline.find_negative_outliers") as mock_det:
            run_anomaly_pipeline(
                as_of_date="2024-05-20",
                settings=mcp_settings,
                save_exports=False,
            )
            mock_det.assert_not_called()

    @patch("myagent.orchestration.pipeline_run.call_mcp_tool")
    def test_empty_anomaly_list(self, mock_call, mcp_settings):
        mock_call.return_value = _mock_result(
            {"check_date": "2024-05-20", "anomaly_list": []}
        )

        result = run_anomaly_pipeline(
            as_of_date="2024-05-20",
            settings=mcp_settings,
            save_exports=False,
        )
        assert len(result.pipeline.anomalies) == 0
        assert "No anomalies" in result.pipeline.formatted_anomaly_block


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestMcpConfigValidation:
    def test_missing_server_path_raises(self):
        settings = Settings(
            retail_data_source="mcp_server",
            wfm_dq_mcp_server_path=None,
            llm_provider="googlegenai",
            google_api_key="test-key",
            daily_report_default_send_slack=False,
        )
        with pytest.raises(ValueError, match="WFM_DQ_MCP_SERVER_PATH"):
            run_anomaly_pipeline(settings=settings, save_exports=False)

    @patch("myagent.orchestration.pipeline_run.call_mcp_tool")
    def test_error_response_raises(self, mock_call, mcp_settings):
        mock_call.return_value = McpToolResult(
            content_text="server error text", is_error=True
        )
        with pytest.raises(RuntimeError, match="MCP server reported error"):
            run_anomaly_pipeline(settings=mcp_settings, save_exports=False)

    @patch("myagent.orchestration.pipeline_run.call_mcp_tool")
    def test_invalid_json_raises(self, mock_call, mcp_settings):
        mock_call.return_value = McpToolResult(content_text="not json")
        with pytest.raises(RuntimeError, match="parse MCP server response"):
            run_anomaly_pipeline(settings=mcp_settings, save_exports=False)


# ---------------------------------------------------------------------------
# local_csv unchanged
# ---------------------------------------------------------------------------


class TestLocalCsvUnchanged:
    def test_local_csv_still_works(self):
        settings = Settings(
            retail_data_source="local_csv",
            llm_provider="googlegenai",
            google_api_key="test-key",
            daily_report_default_send_slack=False,
        )
        result = run_anomaly_pipeline(
            as_of_date="2024-05-20",
            settings=settings,
            save_exports=False,
        )
        assert result.data_source == "local_csv"
        assert result.pipeline.as_of_str == "2024-05-20"
