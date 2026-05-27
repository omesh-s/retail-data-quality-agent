"""ADK retail tool uses MCP-backed adapter behavior."""

from __future__ import annotations

from unittest.mock import patch

from config.settings import Settings
from myagent import retail_tool
from myagent.integrations.mcp_stdio_client import McpToolResult


def _settings(tmp_path) -> Settings:
    script = tmp_path / "server.py"
    script.write_text("# stub")
    return Settings(
        wfm_dq_mcp_server_path_for_adk=str(script),
        llm_provider="googlegenai",
        google_api_key="test-key",
        daily_report_default_send_slack=False,
    )


@patch("myagent.retail_tool.call_mcp_tool")
def test_retail_tool_runs_full_analysis_by_default(mock_call, tmp_path):
    s = _settings(tmp_path)
    mock_call.return_value = McpToolResult(
        content_text='{"check_date":"2026-05-10","total_anomalies":0,"anomaly_list":[]}'
    )
    with patch("myagent.retail_tool.get_settings", return_value=s):
        out = retail_tool.run_retail_data_quality_analysis("Analyze data quality for 2026-05-10")
    assert "DQ analysis 2026-05-10" in out
    kwargs = mock_call.call_args.kwargs
    assert kwargs["tool_name"] == "run_full_dq_analysis"
    assert kwargs["arguments"]["check_date"] == "2026-05-10"


@patch("myagent.retail_tool.call_mcp_tool")
def test_retail_tool_routes_metric_info_queries(mock_call, tmp_path):
    s = _settings(tmp_path)
    mock_call.return_value = McpToolResult(
        content_text='{"metric_cd":"TEST10_TOT","found":true,"formula":"TEST10_TOT = +TEST1 +TEST2 +TEST3"}'
    )
    with patch("myagent.retail_tool.get_settings", return_value=s):
        out = retail_tool.run_retail_data_quality_analysis("What does TEST10_TOT roll up from?")
    assert "Metric TEST10_TOT" in out
    kwargs = mock_call.call_args.kwargs
    assert kwargs["tool_name"] == "get_metric_info"


@patch("myagent.retail_tool.call_mcp_tool")
def test_retail_tool_routes_derived_validation_queries(mock_call, tmp_path):
    s = _settings(tmp_path)
    mock_call.return_value = McpToolResult(
        content_text=(
            '{"metric_cd":"TEST10_TOT","check_date":"2026-05-01","dept_desc":"Bakery",'
            '"component_metric_codes":["TEST1","TEST2","TEST3"],'
            '"store_results":[{"store_id":150,"csv_value":999,"expected_value":600,"error_pct":66.5,"match":false}]}'
        )
    )
    with patch("myagent.retail_tool.get_settings", return_value=s):
        out = retail_tool.run_retail_data_quality_analysis(
            "Validate TEST10_TOT for Bakery on 2026-05-01"
        )
    assert "Derived validation: TEST10_TOT (Bakery) on 2026-05-01" in out
    kwargs = mock_call.call_args.kwargs
    assert kwargs["tool_name"] == "validate_derived_metric"
    assert kwargs["arguments"]["check_date"] == "2026-05-01"


@patch("myagent.retail_tool.call_mcp_tool")
def test_retail_tool_falls_back_to_full_analysis_when_targeted_tool_fails(mock_call, tmp_path):
    s = _settings(tmp_path)
    mock_call.side_effect = [
        RuntimeError("tool missing"),
        McpToolResult(
            content_text='{"check_date":"2026-05-01","total_anomalies":1,"anomaly_list":[{"issue_type":"Derived Metric Mismatch","severity":"High","metric_cd":"TEST10_TOT","store_id":150}]}'
        ),
    ]
    with patch("myagent.retail_tool.get_settings", return_value=s):
        out = retail_tool.run_retail_data_quality_analysis(
            "Validate TEST10_TOT for Bakery on 2026-05-01"
        )
    assert "DQ analysis 2026-05-01" in out
    assert mock_call.call_count == 2
