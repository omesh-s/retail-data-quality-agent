"""CLI: daily anomaly run with top-issues report and optional Slack webhook."""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from app.logging_setup import configure_logging
from config.settings import get_settings
from myagent.orchestration.daily_report import run_daily_report


def main() -> int:
    load_dotenv()
    get_settings.cache_clear()
    configure_logging()
    s = get_settings()

    parser = argparse.ArgumentParser(
        description="Run daily retail data quality detection and optional Slack report."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="As-of date YYYY-MM-DD (default: latest date in metrics data)",
    )
    parser.add_argument(
        "--source",
        choices=["local_csv", "databricks_mcp"],
        default=None,
        help="Override RETAIL_DATA_SOURCE",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Override metrics CSV path (local_csv only)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Global top issues in report (default: DAILY_REPORT_TOP_N)",
    )
    parser.add_argument(
        "--top-n-llm",
        type=int,
        default=None,
        help="Per store/dept cap for pipeline LLM formatting (default: RETAIL_TOP_N)",
    )
    slack_group = parser.add_mutually_exclusive_group()
    slack_group.add_argument(
        "--send-slack",
        action="store_true",
        help="Send Slack webhook (requires SLACK_WEBHOOK_URL)",
    )
    slack_group.add_argument(
        "--no-send-slack",
        action="store_true",
        help="Do not send Slack even if SLACK_ENABLED=true",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON summary to stdout",
    )
    args = parser.parse_args()

    send_slack: bool | None = None
    if args.send_slack:
        send_slack = True
    elif args.no_send_slack:
        send_slack = False

    result = run_daily_report(
        as_of_date=args.date,
        send_slack=send_slack,
        top_n_report=args.top_n,
        top_n_llm=args.top_n_llm,
        data_source=args.source,
        csv_path=args.csv,
        settings=s,
    )

    if args.json:
        payload = {
            "as_of": result.report.as_of,
            "data_source": result.report.data_source,
            "health_summary": result.report.health_summary,
            "total_anomalies": result.report.total_anomalies,
            "severity_counts": result.report.severity_counts,
            "top_issues": result.report.top_issues,
            "export_paths": [str(p) for p in result.export_paths] if result.export_paths else [],
            "slack_sent": result.slack.ok if result.slack else False,
            "slack_error": result.slack.error if result.slack and not result.slack.ok else None,
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"Daily report for {result.report.as_of}")
        print(f"Source: {result.report.data_source}")
        print(f"Summary: {result.report.health_summary}")
        if result.export_paths:
            print(f"Exports: {result.export_paths[0].parent}")
        if result.slack:
            if result.slack.ok:
                print("Slack: delivered")
            else:
                print(f"Slack: failed — {result.slack.error}", file=sys.stderr)
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
