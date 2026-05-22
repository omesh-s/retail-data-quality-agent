"""Send a test Slack webhook message using current .env settings."""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from config.settings import get_settings
from myagent.integrations.slack import send_slack_webhook


def main() -> int:
    load_dotenv()
    get_settings.cache_clear()
    s = get_settings()
    if not s.slack_webhook_url:
        print("SLACK_WEBHOOK_URL is not set.", file=sys.stderr)
        return 1
    result = send_slack_webhook(
        "Retail Data Quality Agent — Slack webhook test.",
        s,
    )
    if result.ok:
        print(f"OK (HTTP {result.status_code})")
        return 0
    print(f"Failed: {result.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
