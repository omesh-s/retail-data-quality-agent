"""Slack Incoming Webhook delivery."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlackDeliveryResult:
    """Outcome of a webhook POST."""

    ok: bool
    status_code: int | None = None
    error: str | None = None


def _redact_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return "<invalid-url>"
    return f"{parsed.scheme}://{parsed.netloc}/…"


def send_slack_webhook(
    message: str,
    settings: Settings,
    *,
    timeout_seconds: float | None = None,
) -> SlackDeliveryResult:
    """POST *message* to the configured Slack Incoming Webhook.

    Args:
        message: Plain-text body (Slack ``text`` field).
        settings: Application settings (must include ``slack_webhook_url``).
        timeout_seconds: HTTP timeout override.

    Returns:
        :class:`SlackDeliveryResult` with success flag and optional error detail.
    """
    url = settings.slack_webhook_url
    if not url:
        return SlackDeliveryResult(ok=False, error="slack_webhook_url is not configured")

    timeout = timeout_seconds if timeout_seconds is not None else settings.slack_timeout_seconds
    payload: dict[str, Any] = {"text": message}

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        if response.status_code >= 400:
            logger.error(
                "Slack webhook failed status=%s host=%s",
                response.status_code,
                _redact_webhook_url(url),
            )
            return SlackDeliveryResult(
                ok=False,
                status_code=response.status_code,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )
        logger.info(
            "Slack webhook delivered status=%s host=%s",
            response.status_code,
            _redact_webhook_url(url),
        )
        return SlackDeliveryResult(ok=True, status_code=response.status_code)
    except requests.RequestException as exc:
        logger.exception(
            "Slack webhook request failed host=%s",
            _redact_webhook_url(url),
        )
        return SlackDeliveryResult(ok=False, error=str(exc))
