"""Internal daily report trigger (scaffold for jobs / Cloud Run)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas.daily_report import DailyReportRunResponse
from myagent.orchestration.daily_report import run_daily_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/daily-report", response_model=DailyReportRunResponse)
def trigger_daily_report(
    as_of_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    send_slack: bool | None = Query(default=None),
    top_n: int | None = Query(default=None),
    source: str | None = Query(default=None, description="local_csv | databricks_mcp"),
) -> DailyReportRunResponse:
    """Run the same orchestration as ``run_daily_report.py`` (no LLM summary)."""
    try:
        result = run_daily_report(
            as_of_date=as_of_date,
            send_slack=send_slack,
            top_n_report=top_n,
            data_source=source,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("daily report failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    slack_sent = bool(result.slack and result.slack.ok)
    slack_error = result.slack.error if result.slack and not result.slack.ok else None

    return DailyReportRunResponse(
        as_of=result.report.as_of,
        data_source=result.report.data_source,
        health_summary=result.report.health_summary,
        total_anomalies=result.report.total_anomalies,
        severity_counts=result.report.severity_counts,
        top_issue_count=len(result.report.top_issues),
        slack_sent=slack_sent,
        slack_error=slack_error,
    )
