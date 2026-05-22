"""Settings parsing and validation."""

from __future__ import annotations

import pytest

from config.settings import Settings


def test_defaults_local_csv():
    s = Settings(
        llm_provider="googlegenai",
        retail_data_source="local_csv",
        daily_report_default_send_slack=False,
        slack_enabled=False,
    )
    assert s.retail_data_source == "local_csv"
    assert s.llm_provider == "googlegenai"


def test_validate_llm_openai_requires_key():
    s = Settings(llm_provider="openai", openai_api_key=None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        s.validate_llm_credentials()


def test_slack_auto_send_flags():
    s = Settings(
        slack_webhook_url="https://hooks.slack.com/x",
        daily_report_default_send_slack=True,
        slack_enabled=False,
    )
    from myagent.orchestration.daily_report import resolve_send_slack

    assert resolve_send_slack(s, None) is True
