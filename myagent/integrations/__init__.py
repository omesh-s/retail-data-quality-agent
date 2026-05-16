"""Outbound integrations (Slack, etc.)."""

from myagent.integrations.slack import SlackDeliveryResult, send_slack_webhook

__all__ = ["SlackDeliveryResult", "send_slack_webhook"]
