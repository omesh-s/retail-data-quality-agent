"""Schemas for daily report API responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DailyReportRunResponse(BaseModel):
    """Response from triggering a daily report run."""

    as_of: str
    data_source: str
    health_summary: str
    total_anomalies: int
    severity_counts: dict[str, int]
    top_issue_count: int
    slack_sent: bool
    slack_error: str | None = None


class DailyReportTriggerRequest(BaseModel):
    """Optional body for daily report trigger (query params also supported)."""

    as_of_date: str | None = Field(default=None, description="YYYY-MM-DD")
    send_slack: bool | None = Field(default=None)
    top_n: int | None = Field(default=None)
