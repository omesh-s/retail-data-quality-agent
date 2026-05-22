"""Daily anomaly run: data source → pipeline → top-issues report → optional Slack."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from config.settings import Settings, get_settings
from myagent.data_sources.factory import DataSourceKind
from myagent.integrations.slack import SlackDeliveryResult, send_slack_webhook
from myagent.orchestration.pipeline_run import run_anomaly_pipeline
from myagent.pipeline import OUTPUT_DIR, PipelineResult
from myagent.reporting.daily_report_format import (
    DailyReportPayload,
    build_daily_report_payload,
    format_slack_message,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DailyReportResult:
    """Outcome of :func:`run_daily_report`."""

    pipeline: PipelineResult
    report: DailyReportPayload
    export_paths: tuple[Path, Path] | None
    slack: SlackDeliveryResult | None
    slack_message: str | None
    data_source: str


def resolve_send_slack(settings: Settings, send_slack: bool | None) -> bool:
    """Decide whether to POST to Slack for this run."""
    if send_slack is False:
        return False
    if send_slack is True:
        if not settings.slack_webhook_url:
            logger.warning("--send-slack requested but SLACK_WEBHOOK_URL is unset")
            return False
        return True
    return bool(settings.slack_enabled and settings.slack_webhook_url)


def run_daily_report(
    *,
    as_of_date: str | None = None,
    send_slack: bool | None = None,
    top_n_report: int | None = None,
    top_n_llm: int | None = None,
    data_source: DataSourceKind | str | None = None,
    csv_path: str | Path | None = None,
    settings: Settings | None = None,
    save_exports: bool = True,
    output_dir: str | Path | None = None,
) -> DailyReportResult:
    """Run the full daily workflow used by CLI, jobs, and future HTTP triggers."""
    s = settings or get_settings()

    run_result = run_anomaly_pipeline(
        as_of_date=as_of_date,
        user_message="",
        settings=s,
        data_source=data_source,
        csv_path=csv_path,
        top_n=top_n_llm,
        save_exports=save_exports,
        output_dir=output_dir,
    )
    pipeline_result = run_result.pipeline

    report_top_n = top_n_report if top_n_report is not None else s.daily_report_top_n
    report = build_daily_report_payload(
        pipeline_result.anomalies,
        as_of=pipeline_result.as_of_str,
        data_source=run_result.data_source,
        top_n=report_top_n,
    )

    export_paths: tuple[Path, Path] | None = None
    if save_exports:
        stem = f"raw_anomalies_{pipeline_result.as_of_str}"
        out = Path(output_dir) if output_dir else OUTPUT_DIR
        export_paths = (out / f"{stem}.json", out / f"{stem}.csv")

    slack_result: SlackDeliveryResult | None = None
    slack_text: str | None = None
    if resolve_send_slack(s, send_slack):
        slack_text = format_slack_message(report)
        slack_result = send_slack_webhook(slack_text, s)
        if not slack_result.ok:
            logger.error("Slack delivery failed: %s", slack_result.error)

    return DailyReportResult(
        pipeline=pipeline_result,
        report=report,
        export_paths=export_paths,
        slack=slack_result,
        slack_message=slack_text,
        data_source=run_result.data_source,
    )
