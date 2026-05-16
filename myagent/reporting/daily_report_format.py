"""Build daily top-issues payload and Slack-friendly text."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

_SEVERITY_RANK = {"High": 0, "Medium": 1, "Low": 2}


@dataclass(frozen=True)
class DailyReportPayload:
    """Structured daily report for Slack, API, or jobs."""

    as_of: str
    health_summary: str
    total_anomalies: int
    severity_counts: dict[str, int]
    top_issues: list[dict[str, Any]]
    data_source: str


def compute_health_summary(anomalies: list[dict]) -> tuple[str, dict[str, int]]:
    """Return a one-line summary and severity counts."""
    if not anomalies:
        return "No anomalies detected.", {}
    counts = Counter(str(a.get("severity") or "Low") for a in anomalies)
    ordered = {k: counts.get(k, 0) for k in ("High", "Medium", "Low") if counts.get(k)}
    for k, v in counts.items():
        if k not in ordered:
            ordered[k] = v
    parts = [f"{v} {k}" for k, v in ordered.items()]
    summary = f"{len(anomalies)} anomalies ({', '.join(parts)})"
    return summary, dict(ordered)


def select_top_issues(anomalies: list[dict], k: int) -> list[dict]:
    """Global top *k* issues by severity then impact_score."""

    def sort_key(rec: dict) -> tuple[int, float]:
        sev = str(rec.get("severity") or "Low")
        return (_SEVERITY_RANK.get(sev, 2), -float(rec.get("impact_score") or 0.0))

    return sorted(anomalies, key=sort_key)[: max(k, 0)]


def build_daily_report_payload(
    anomalies: list[dict],
    *,
    as_of: str,
    data_source: str,
    top_n: int = 10,
) -> DailyReportPayload:
    """Aggregate counts and top issues for reporting channels."""
    health_summary, severity_counts = compute_health_summary(anomalies)
    top = select_top_issues(anomalies, top_n)
    return DailyReportPayload(
        as_of=as_of,
        health_summary=health_summary,
        total_anomalies=len(anomalies),
        severity_counts=severity_counts,
        top_issues=top,
        data_source=data_source,
    )


def _format_issue_line(index: int, rec: dict) -> str:
    store = rec.get("storeid", "?")
    dept = rec.get("deptname", "?")
    mcode = rec.get("metriccode", "?")
    issue = rec.get("issue_type", "?")
    sev = rec.get("severity", "?")
    when = rec.get("date_or_range", "?")
    detail = (rec.get("details") or "")[:200]
    return (
        f"{index}. [{sev}] Store {store} / {dept} — {issue} — {mcode} @ {when}\n"
        f"   {detail}"
    )


def format_slack_message(payload: DailyReportPayload) -> str:
    """Plain-text Slack message (Incoming Webhook)."""
    lines = [
        "*Retail Data Quality — Daily Report*",
        f"As-of date: {payload.as_of}",
        f"Data source: {payload.data_source}",
        f"Summary: {payload.health_summary}",
        "",
    ]
    if not payload.top_issues:
        lines.append("_No top issues to display._")
    else:
        lines.append(f"Top {len(payload.top_issues)} issues:")
        for i, rec in enumerate(payload.top_issues, start=1):
            lines.append(_format_issue_line(i, rec))
    return "\n".join(lines)
