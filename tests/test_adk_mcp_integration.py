"""Tests for the ADK MCP toolset integration in myagent/agent.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.settings import Settings


# ---------------------------------------------------------------------------
# Graceful fallback when MCP is not configured
# ---------------------------------------------------------------------------


class TestMcpNotConfigured:
    """When WFM_DQ_MCP_SERVER_PATH_FOR_ADK is unset, agent loads with pipeline tool only."""

    def test_build_mcp_toolset_returns_none_when_unset(self):
        settings = Settings(
            wfm_dq_mcp_server_path_for_adk=None,
            llm_provider="googlegenai",
            google_api_key="test-key",
            daily_report_default_send_slack=False,
        )
        with patch("myagent.agent.get_settings", return_value=settings):
            from myagent.agent import _build_mcp_toolset

            assert _build_mcp_toolset() is None

    def test_build_mcp_toolset_returns_none_when_path_missing(self, tmp_path):
        settings = Settings(
            wfm_dq_mcp_server_path_for_adk=str(tmp_path / "nonexistent.py"),
            llm_provider="googlegenai",
            google_api_key="test-key",
            daily_report_default_send_slack=False,
        )
        with patch("myagent.agent.get_settings", return_value=settings):
            from myagent.agent import _build_mcp_toolset

            assert _build_mcp_toolset() is None

    def test_build_tools_always_includes_pipeline_tool(self):
        settings = Settings(
            wfm_dq_mcp_server_path_for_adk=None,
            llm_provider="googlegenai",
            google_api_key="test-key",
            daily_report_default_send_slack=False,
        )
        with patch("myagent.agent.get_settings", return_value=settings):
            from myagent.agent import _build_tools

            tools = _build_tools()
            assert len(tools) == 1
            assert tools[0].__class__.__name__ == "FunctionTool"


# ---------------------------------------------------------------------------
# MCP toolset creation when configured
# ---------------------------------------------------------------------------


class TestMcpConfigured:
    """When WFM_DQ_MCP_SERVER_PATH_FOR_ADK points to a valid script, MCPToolset is added."""

    @patch("myagent.agent.McpToolset", create=True)
    def test_build_mcp_toolset_creates_toolset(self, mock_cls, tmp_path):
        fake_script = tmp_path / "server.py"
        fake_script.write_text("# stub")

        settings = Settings(
            wfm_dq_mcp_server_path_for_adk=str(fake_script),
            wfm_dq_mcp_server_timeout_for_adk=15.0,
            llm_provider="googlegenai",
            google_api_key="test-key",
            daily_report_default_send_slack=False,
        )

        mock_toolset = MagicMock()
        mock_cls.return_value = mock_toolset

        with patch("myagent.agent.get_settings", return_value=settings):
            # Patch the imports inside _build_mcp_toolset
            with patch.dict(
                "sys.modules",
                {
                    "google.adk.tools.mcp_tool.mcp_toolset": MagicMock(
                        McpToolset=mock_cls,
                        StdioConnectionParams=MagicMock(),
                    ),
                    "mcp": MagicMock(StdioServerParameters=MagicMock()),
                },
            ):
                from myagent.agent import _build_mcp_toolset

                result = _build_mcp_toolset()

        assert result is mock_toolset

    def test_build_tools_includes_mcp_when_configured(self, tmp_path):
        fake_script = tmp_path / "server.py"
        fake_script.write_text("# stub")

        settings = Settings(
            wfm_dq_mcp_server_path_for_adk=str(fake_script),
            llm_provider="googlegenai",
            google_api_key="test-key",
            daily_report_default_send_slack=False,
        )

        mock_toolset = MagicMock()

        with patch("myagent.agent.get_settings", return_value=settings):
            with patch("myagent.agent._build_mcp_toolset", return_value=mock_toolset):
                from myagent.agent import _build_tools

                tools = _build_tools()

        assert len(tools) == 2
        assert tools[0].__class__.__name__ == "FunctionTool"
        assert tools[1] is mock_toolset


# ---------------------------------------------------------------------------
# Instruction text
# ---------------------------------------------------------------------------


class TestInstruction:
    def test_base_instruction_when_mcp_unset(self):
        settings = Settings(
            wfm_dq_mcp_server_path_for_adk=None,
            llm_provider="googlegenai",
            google_api_key="test-key",
            daily_report_default_send_slack=False,
        )
        with patch("myagent.agent.get_settings", return_value=settings):
            from myagent.agent import _build_instruction

            text = _build_instruction()
            assert "run_retail_data_quality_analysis" in text
            assert "get_available_dates" not in text

    def test_mcp_addendum_when_configured(self, tmp_path):
        fake_script = tmp_path / "server.py"
        fake_script.write_text("# stub")

        settings = Settings(
            wfm_dq_mcp_server_path_for_adk=str(fake_script),
            llm_provider="googlegenai",
            google_api_key="test-key",
            daily_report_default_send_slack=False,
        )
        with patch("myagent.agent.get_settings", return_value=settings):
            from myagent.agent import _build_instruction

            text = _build_instruction()
            assert "run_retail_data_quality_analysis" in text
            assert "get_available_dates" in text
            assert "run_full_dq_analysis" in text
            assert "get_metric_info" in text
