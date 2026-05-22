"""Daily report orchestration (no real Slack)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config.settings import Settings
from myagent.orchestration.daily_report import resolve_send_slack, run_daily_report


def test_resolve_send_slack_flags():
    s = Settings(slack_enabled=True, slack_webhook_url="https://hooks.slack.com/x")
    assert resolve_send_slack(s, None) is True
    assert resolve_send_slack(s, False) is False
    assert resolve_send_slack(s, True) is True


@patch("myagent.orchestration.daily_report.send_slack_webhook")
def test_run_daily_report_local_csv_no_slack(mock_slack, sample_csv_path, tmp_path):
    s = Settings(
        retail_data_source="local_csv",
        retail_metrics_csv=sample_csv_path,
        slack_enabled=False,
    )
    result = run_daily_report(
        as_of_date="2024-05-20",
        send_slack=False,
        settings=s,
        save_exports=True,
        output_dir=tmp_path,
    )
    mock_slack.assert_not_called()
    assert result.report.as_of == "2024-05-20"
    assert result.data_source == "local_csv"
    assert result.report.data_source == "local_csv"
    assert result.report.total_anomalies >= 0
    assert result.export_paths is not None
    assert result.export_paths[0].exists()


@patch("myagent.orchestration.daily_report.send_slack_webhook")
def test_run_daily_report_sends_slack_when_requested(mock_slack, sample_csv_path, tmp_path):
    from myagent.integrations.slack import SlackDeliveryResult

    mock_slack.return_value = SlackDeliveryResult(ok=True, status_code=200)
    s = Settings(
        retail_data_source="local_csv",
        retail_metrics_csv=sample_csv_path,
        slack_webhook_url="https://hooks.slack.com/services/T/B/x",
    )
    result = run_daily_report(
        as_of_date="2024-05-20",
        send_slack=True,
        settings=s,
        save_exports=False,
        output_dir=tmp_path,
    )
    mock_slack.assert_called_once()
    assert result.slack is not None
    assert result.slack.ok is True
