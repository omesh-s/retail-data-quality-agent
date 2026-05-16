"""Daily report formatting."""

from __future__ import annotations

from myagent.reporting.daily_report_format import (
    build_daily_report_payload,
    compute_health_summary,
    format_slack_message,
    select_top_issues,
)


def test_compute_health_summary_empty():
    summary, counts = compute_health_summary([])
    assert "No anomalies" in summary
    assert counts == {}


def test_select_top_issues_orders_by_severity_and_impact():
    anomalies = [
        {"severity": "Low", "impact_score": 0.99, "storeid": 1},
        {"severity": "High", "impact_score": 0.5, "storeid": 2},
        {"severity": "High", "impact_score": 0.9, "storeid": 3},
    ]
    top = select_top_issues(anomalies, 2)
    assert top[0]["storeid"] == 3
    assert top[1]["storeid"] == 2


def test_slack_message_contains_key_fields():
    payload = build_daily_report_payload(
        [
            {
                "storeid": 4,
                "deptname": "Seafood",
                "metriccode": "SYSTEM_ON",
                "issue_type": "Continuity Gap",
                "severity": "High",
                "date_or_range": "2024-05-01 to 2024-05-07",
                "details": "7-day gap",
                "impact_score": 0.9,
            }
        ],
        as_of="2024-05-20",
        data_source="local_csv",
        top_n=5,
    )
    text = format_slack_message(payload)
    assert "2024-05-20" in text
    assert "Seafood" in text
    assert "Continuity Gap" in text
