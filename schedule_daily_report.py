"""Run daily report on a schedule (local dev) or once for cron/Cloud Scheduler."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from app.logging_setup import configure_logging
from config.settings import get_settings
from myagent.orchestration.daily_report import run_daily_report

logger = logging.getLogger(__name__)


def _seconds_until(hour: int, minute: int, tz_name: str) -> float:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_once(*, as_of_date: str | None, send_slack: bool | None) -> int:
    result = run_daily_report(as_of_date=as_of_date, send_slack=send_slack)
    print(f"Daily report for {result.report.as_of} ({result.data_source})")
    print(result.report.health_summary)
    if result.slack and not result.slack.ok:
        print(f"Slack failed: {result.slack.error}", file=sys.stderr)
        return 1
    if result.slack and result.slack.ok:
        print("Slack: delivered")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    get_settings.cache_clear()
    configure_logging()
    s = get_settings()

    parser = argparse.ArgumentParser(
        description="Run daily retail report once or on a simple daily loop."
    )
    parser.add_argument("--date", default=None, help="As-of YYYY-MM-DD")
    parser.add_argument("--once", action="store_true", help="Run once and exit (default)")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run daily at DAILY_REPORT_HOUR:MINUTE in DAILY_REPORT_TIMEZONE",
    )
    parser.add_argument("--send-slack", action="store_true", help="Force Slack on")
    parser.add_argument("--no-send-slack", action="store_true", help="Force Slack off")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if DAILY_REPORT_ENABLED=false",
    )
    args = parser.parse_args(argv)

    if not args.force and not s.daily_report_enabled and args.loop:
        logger.error("DAILY_REPORT_ENABLED=false; use --force or enable in .env")
        return 1

    send_slack: bool | None = None
    if args.send_slack:
        send_slack = True
    elif args.no_send_slack:
        send_slack = False

    if args.loop:
        logger.info(
            "Scheduler loop: daily at %02d:%02d %s",
            s.daily_report_hour,
            s.daily_report_minute,
            s.daily_report_timezone,
        )
        if s.daily_report_schedule_cron:
            logger.warning(
                "DAILY_REPORT_SCHEDULE_CRON is set but not parsed by this script; "
                "use system cron to call: python schedule_daily_report.py --once"
            )
        while True:
            wait = _seconds_until(
                s.daily_report_hour, s.daily_report_minute, s.daily_report_timezone
            )
            logger.info("Sleeping %.0f seconds until next run", wait)
            time.sleep(wait)
            code = run_once(as_of_date=args.date, send_slack=send_slack)
            if code != 0:
                logger.error("Daily report run failed with code %s", code)
    return run_once(as_of_date=args.date, send_slack=send_slack)


if __name__ == "__main__":
    raise SystemExit(main())
