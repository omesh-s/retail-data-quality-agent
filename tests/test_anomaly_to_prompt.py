"""Tests for myagent/anomaly_to_prompt.py — field-aware formatting."""

from __future__ import annotations

from myagent.anomaly_to_prompt import (
    format_anomalies_for_llm,
    format_anomalies_for_llm_by_issue,
)


# ---------------------------------------------------------------------------
# Fixtures: MCP-style (rich fields) and local-pipeline-style (legacy fields)
# ---------------------------------------------------------------------------

_MCP_CONTINUITY_SYSTEMIC = {
    "issue_type": "Continuity Gap",
    "dept_desc": "Market",
    "metric_cd": "MKT_SAT_UN",
    "store_id": 101,
    "severity": "High",
    "severity_reason": "Systemic gap across 5+ stores",
    "consecutive_missing_days": 8,
    "continuity_scope": "systemic",
    "affected_store_count": 5,
    "first_missing_date": "2026-05-10",
    "last_missing_date": "2026-05-17",
    "priority": -30,
}

_MCP_CONTINUITY_ISOLATED = {
    "issue_type": "Continuity Gap",
    "dept_desc": "Deli",
    "metric_cd": "DELI_AM",
    "store_id": 404,
    "severity": "High",
    "severity_reason": "Gap of 8 consecutive days",
    "consecutive_missing_days": 8,
    "continuity_scope": "isolated",
    "affected_store_count": 1,
    "first_missing_date": "2026-05-10",
    "last_missing_date": "2026-05-17",
    "priority": 0,
}

_MCP_NEGATIVE_LARGE = {
    "issue_type": "Negative Outlier",
    "dept_desc": "Deli",
    "metric_cd": "DELI_AM",
    "store_id": 623,
    "severity": "High",
    "severity_reason": "Extreme negative (-1000), 5.0x historical mean",
    "metric_value": -1000,
    "negative_magnitude": 1000,
    "historical_mean": 200,
    "historical_ratio": 5.0,
    "priority": -20,
}

_MCP_NEGATIVE_SMALL = {
    "issue_type": "Negative Outlier",
    "dept_desc": "Bakery",
    "metric_cd": "BKY_3A_UN",
    "store_id": 100,
    "severity": "Medium",
    "severity_reason": "Small negative (-3) on positive-only metric",
    "metric_value": -3,
    "negative_magnitude": 3,
    "historical_mean": 50,
    "historical_ratio": 0.06,
    "priority": 100,
}

_MCP_DERIVED_MISMATCH = {
    "issue_type": "Derived Metric Mismatch",
    "dept_desc": "Bakery",
    "metric_cd": "TEST10_TOT",
    "store_id": 150,
    "severity": "High",
    "severity_reason": "Derived mismatch (66.5% error)",
    "csv_value": 999,
    "expected_value": 600,
    "absolute_error": 399,
    "error_pct": 66.5,
    "component_metric_codes": ["TEST1", "TEST2", "TEST3"],
    "priority": -50,
}

_LOCAL_PIPELINE_SPIKE = {
    "issue_type": "Positive Spike",
    "storeid": 42,
    "deptname": "Market",
    "metriccode": "MKT_SAT_UN",
    "metricvalue": 999.99,
    "severity": "High",
    "impact_score": 0.85,
    "z_score": 90.0,
}

_LOCAL_PIPELINE_GAP = {
    "issue_type": "Continuity Gap",
    "storeid": 7,
    "deptname": "Bakery",
    "metriccode": "BKY_3A_UN",
    "severity": "Medium",
    "impact_score": 0.50,
    "streak_length": 10,
}


# ---------------------------------------------------------------------------
# Basic formatting tests
# ---------------------------------------------------------------------------


class TestBasicFormatting:
    def test_empty_returns_no_anomalies(self):
        result = format_anomalies_for_llm([])
        assert result == "No anomalies detected."

    def test_single_local_pipeline_record(self):
        result = format_anomalies_for_llm([_LOCAL_PIPELINE_SPIKE])
        assert "Store 42" in result
        assert "Market" in result
        assert "Positive Spike" in result
        assert "z=90.0" in result

    def test_single_mcp_record(self):
        result = format_anomalies_for_llm([_MCP_DERIVED_MISMATCH])
        assert "Store 150" in result
        assert "TEST10_TOT" in result
        assert "Derived Metric Mismatch" in result

    def test_no_crash_on_minimal_record(self):
        result = format_anomalies_for_llm([{"issue_type": "Unknown", "severity": "Low"}])
        assert "Unknown" in result


# ---------------------------------------------------------------------------
# Rich MCP field usage
# ---------------------------------------------------------------------------


class TestRichFieldUsage:
    def test_continuity_scope_appears_when_present(self):
        result = format_anomalies_for_llm([_MCP_CONTINUITY_SYSTEMIC, _MCP_CONTINUITY_ISOLATED])
        assert "systemic" in result.lower()
        assert "isolated" in result.lower()
        assert "5+" in result  # severity_reason says "5+ stores"

    def test_scope_header_generated(self):
        result = format_anomalies_for_llm([_MCP_CONTINUITY_SYSTEMIC, _MCP_CONTINUITY_ISOLATED])
        assert "Continuity breakdown:" in result

    def test_severity_reason_used_instead_of_generic_fact(self):
        result = format_anomalies_for_llm([_MCP_NEGATIVE_LARGE])
        assert "Extreme negative" in result

    def test_derived_shows_error_info(self):
        result = format_anomalies_for_llm([_MCP_DERIVED_MISMATCH])
        assert "Derived mismatch" in result
        assert "66.5%" in result

    def test_derived_fallback_when_no_severity_reason(self):
        """When severity_reason is absent, detailed csv/expected facts appear."""
        rec = {**_MCP_DERIVED_MISMATCH}
        del rec["severity_reason"]
        result = format_anomalies_for_llm([rec])
        assert "stored=999" in result
        assert "expected=600" in result
        assert "err=66.5%" in result
        assert "TEST1+TEST2+TEST3" in result

    def test_negative_magnitude_shown(self):
        result = format_anomalies_for_llm([_MCP_NEGATIVE_LARGE])
        # severity_reason takes precedence, but check it's using it
        assert "-1000" in result


# ---------------------------------------------------------------------------
# Graceful fallback when rich fields absent
# ---------------------------------------------------------------------------


class TestFieldFallback:
    def test_no_continuity_scope_no_crash(self):
        rec = {
            "issue_type": "Continuity Gap",
            "store_id": 99,
            "dept_desc": "Produce",
            "metric_cd": "PRO_VOL_UN",
            "severity": "Medium",
            "consecutive_missing_days": 7,
        }
        result = format_anomalies_for_llm([rec])
        assert "Continuity Gap" in result
        assert "7d gap" in result
        # No scope header when no scope fields
        assert "Continuity breakdown:" not in result

    def test_no_negative_magnitude_no_crash(self):
        rec = {
            "issue_type": "Negative Outlier",
            "store_id": 99,
            "dept_desc": "Deli",
            "metric_cd": "DELI_UN",
            "severity": "High",
            "metric_value": -500,
        }
        result = format_anomalies_for_llm([rec])
        assert "val=-500" in result

    def test_no_derived_fields_no_crash(self):
        rec = {
            "issue_type": "Derived Metric Mismatch",
            "store_id": 150,
            "dept_desc": "Bakery",
            "metric_cd": "TEST10_TOT",
            "severity": "High",
        }
        result = format_anomalies_for_llm([rec])
        assert "Derived Metric Mismatch" in result

    def test_no_priority_no_crash(self):
        recs = [_LOCAL_PIPELINE_SPIKE, _LOCAL_PIPELINE_GAP]
        result = format_anomalies_for_llm(recs)
        assert "Positive Spike" in result
        assert "Continuity Gap" in result


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    def test_mcp_priority_ordering(self):
        recs = [_MCP_NEGATIVE_SMALL, _MCP_DERIVED_MISMATCH, _MCP_CONTINUITY_SYSTEMIC]
        result = format_anomalies_for_llm(recs)
        lines = result.strip().split("\n")
        # Derived mismatch has priority -50, systemic has -30, small neg has 100
        # So derived should appear before small neg
        derived_line = next(i for i, l in enumerate(lines) if "TEST10_TOT" in l)
        neg_line = next(i for i, l in enumerate(lines) if "BKY_3A_UN" in l)
        assert derived_line < neg_line

    def test_local_pipeline_falls_back_to_severity(self):
        high = {**_LOCAL_PIPELINE_SPIKE, "severity": "High"}
        low = {**_LOCAL_PIPELINE_GAP, "severity": "Low"}
        result = format_anomalies_for_llm([low, high])
        lines = result.strip().split("\n")
        high_idx = next(i for i, l in enumerate(lines) if "MKT_SAT_UN" in l)
        low_idx = next(i for i, l in enumerate(lines) if "BKY_3A_UN" in l)
        assert high_idx < low_idx


# ---------------------------------------------------------------------------
# Issue-type filtering
# ---------------------------------------------------------------------------


class TestIssueFiltering:
    def test_filter_continuity_only(self):
        recs = [_MCP_CONTINUITY_SYSTEMIC, _MCP_NEGATIVE_LARGE, _MCP_DERIVED_MISMATCH]
        result = format_anomalies_for_llm_by_issue(recs, "Continuity")
        assert "Continuity Gap" in result
        assert "Negative Outlier" not in result
        assert "Derived Metric Mismatch" not in result

    def test_filter_negative_only(self):
        recs = [_MCP_CONTINUITY_SYSTEMIC, _MCP_NEGATIVE_LARGE, _MCP_DERIVED_MISMATCH]
        result = format_anomalies_for_llm_by_issue(recs, "Negative")
        assert "Negative Outlier" in result
        assert "Continuity Gap" not in result

    def test_filter_derived_only(self):
        recs = [_MCP_CONTINUITY_SYSTEMIC, _MCP_NEGATIVE_LARGE, _MCP_DERIVED_MISMATCH]
        result = format_anomalies_for_llm_by_issue(recs, "Derived")
        assert "Derived Metric Mismatch" in result
        assert "Negative Outlier" not in result

    def test_no_match_returns_message(self):
        result = format_anomalies_for_llm_by_issue([_MCP_NEGATIVE_LARGE], "Grain")
        assert "No Grain anomalies found." in result

    def test_none_filter_returns_all(self):
        recs = [_MCP_CONTINUITY_SYSTEMIC, _MCP_NEGATIVE_LARGE]
        result = format_anomalies_for_llm_by_issue(recs, None)
        assert "Continuity Gap" in result
        assert "Negative Outlier" in result


# ---------------------------------------------------------------------------
# Compactness: new format should be shorter than verbose dumps
# ---------------------------------------------------------------------------


class TestCompactness:
    def test_prompt_is_compact(self):
        recs = [
            _MCP_CONTINUITY_SYSTEMIC,
            _MCP_CONTINUITY_ISOLATED,
            _MCP_NEGATIVE_LARGE,
            _MCP_NEGATIVE_SMALL,
            _MCP_DERIVED_MISMATCH,
        ]
        result = format_anomalies_for_llm(recs)
        lines = [l for l in result.strip().split("\n") if l.strip()]
        # 5 anomalies across 4 store/dept groups + headers + scope header
        # should be roughly 10-15 lines, not 50+
        assert len(lines) <= 20
        assert len(result) < 1500
