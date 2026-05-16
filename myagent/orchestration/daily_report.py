"""Daily anomaly run: data source → pipeline → top-issues report → optional Slack."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from config.settings import Settings, get_settings
from myagent.data_sources.factory import DataSourceKind, get_metrics_data_source
from myagent.integrations.slack import SlackDeliveryResult, send_slack_webhook
from myagent.pipeline import OUTPUT_DIR, PipelineResult, run_detection_pipeline_from_dataframe
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
    """Run the full daily workflow used by CLI, jobs, and future HTTP triggers.

    1. Resolve metrics via configured data source.
    2. Run :func:`run_detection_pipeline_from_dataframe` (same detectors/enrichment as CLI).
    3. Build top-issues report payload.
    4. Optionally deliver Slack Incoming Webhook message.

    Args:
        as_of_date: Analysis day ``YYYY-MM-DD`` (else latest date in data).
        send_slack: ``True``/``False`` override; ``None`` uses ``SLACK_ENABLED`` + URL.
        top_n_report: Global top issues in the report (default from settings).
        top_n_llm: Per store/dept cap for formatted prompt (default from settings).
        data_source: Override ``RETAIL_DATA_SOURCE``.
        csv_path: Override CSV path when using ``local_csv``.
        settings: Optional settings instance.
        save_exports: Write ``output/raw_anomalies_*`` files.
        output_dir: Export directory override.

    Returns:
        :class:`DailyReportResult` with pipeline output and delivery metadata.
    """
    s = settings or get_settings()
    provider = get_metrics_data_source(s, source=data_source, csv_path=str(csv_path) if csv_path else None)
    logger.info("Daily report using data source: %s", provider.name)

    metrics_df = provider.fetch_metrics()

    llm_top_n = top_n_llm if top_n_llm is not None else s.retail_top_n
    pipeline_result = run_detection_pipeline_from_dataframe(
        metrics_df,
        as_of_date=as_of_date,
        user_message="",
        history_days=s.retail_history_days,
        z_threshold=s.retail_z_threshold,
        grain_min_distinct_days=s.retail_grain_min_distinct,
        grain_min_avg=s.retail_grain_min_avg,
        top_n=llm_top_n,
        save_exports=save_exports,
        output_dir=output_dir or OUTPUT_DIR,
    )

    report_top_n = top_n_report if top_n_report is not None else s.daily_report_top_n
    report = build_daily_report_payload(
        pipeline_result.anomalies,
        as_of=pipeline_result.as_of_str,
        data_source=provider.name,
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
    )
