"""Settings parsing and validation."""

from __future__ import annotations

import pytest

from config.settings import Settings


def test_defaults_mcp_first():
    s = Settings(
        llm_provider="googlegenai",
    )
    assert s.llm_provider == "googlegenai"
    assert s.log_format in ("console", "json")
    assert s.service_host == "127.0.0.1"
    assert s.service_port == 8080


def test_validate_llm_openai_requires_key():
    s = Settings(llm_provider="openai", openai_api_key=None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        s.validate_llm_credentials()


def test_mcp_settings_defaults():
    s = Settings(
        wfm_dq_mcp_server_path_for_adk="C:/tmp/server.py",
    )
    assert s.wfm_dq_mcp_server_path_for_adk == "C:/tmp/server.py"
    assert s.wfm_dq_mcp_server_timeout_for_adk == 90.0
    assert s.wfm_dq_mcp_transport_for_adk == "stdio"


def test_validate_mcp_runtime_requires_path():
    s = Settings(
        wfm_dq_mcp_server_path_for_adk=None,
        llm_provider="googlegenai",
    )
    with pytest.raises(ValueError, match="WFM_DQ_MCP_SERVER_PATH_FOR_ADK"):
        s.validate_mcp_runtime()


def test_validate_sse_runtime_requires_url():
    s = Settings(
        wfm_dq_mcp_transport_for_adk="sse",
        wfm_dq_mcp_server_url_for_adk=None,
        llm_provider="googlegenai",
    )
    with pytest.raises(ValueError, match="WFM_DQ_MCP_SERVER_URL_FOR_ADK"):
        s.validate_mcp_runtime()


def test_validate_sse_runtime_requires_token_when_flag_enabled():
    s = Settings(
        wfm_dq_mcp_transport_for_adk="sse",
        wfm_dq_mcp_server_url_for_adk="http://127.0.0.1:8000/sse",
        wfm_dq_mcp_require_auth_for_sse=True,
        wfm_dq_mcp_auth_token_for_adk=None,
        llm_provider="googlegenai",
    )
    with pytest.raises(ValueError, match="WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK"):
        s.validate_mcp_runtime()
