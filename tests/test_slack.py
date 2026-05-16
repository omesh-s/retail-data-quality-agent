"""Slack webhook client (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from config.settings import Settings
from myagent.integrations.slack import send_slack_webhook


@patch("myagent.integrations.slack.requests.post")
def test_send_slack_success(mock_post):
    mock_post.return_value = MagicMock(status_code=200, text="ok")
    s = Settings(slack_webhook_url="https://hooks.slack.com/services/T/B/x")
    result = send_slack_webhook("hello", s)
    assert result.ok is True
    mock_post.assert_called_once()
    assert mock_post.call_args.kwargs["json"]["text"] == "hello"


def test_send_slack_missing_url():
    s = Settings(slack_webhook_url=None)
    result = send_slack_webhook("hello", s)
    assert result.ok is False
    assert "not configured" in (result.error or "")
