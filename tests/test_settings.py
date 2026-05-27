"""Settings parsing and validation."""

from __future__ import annotations

import pytest

from config.settings import Settings


def test_defaults_local_csv():
    s = Settings(
        llm_provider="googlegenai",
    )
    assert s.llm_provider == "googlegenai"
    assert s.log_format in ("console", "json")


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
