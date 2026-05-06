"""Severity, impact scores, and business-impact hints for anomaly records."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from myagent.anomaly_detector import COL_DEPT, COL_METRIC, COL_STORE, COL_VALUE, _norm_metric_code

_HIGH_THRESHOLD = 0.67
_MEDIUM_THRESHOLD = 0.34

# Rough "large store" proxy: max daily revenue in window (currency units).
_LARGE_STORE_REVENUE = 5000.0


def severity_from_impact_score(score: float) -> str:
    """Map a 0–1 impact score to High / Medium / Low."""
    if score >= _HIGH_THRESHOLD:
        return "High"
    if score >= _MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"


def _store_max_revenue_usd(df: pd.DataFrame) -> dict[Any, float]:
    if df.empty or COL_VALUE not in df.columns:
        return {}
    rev = df[
        df[COL_METRIC].map(lambda m: _norm_metric_code(m) == "REVENUEUSD")
        & df[COL_VALUE].notna()
    ]
    if rev.empty:
        return {}
    return rev.groupby(COL_STORE, sort=False)[COL_VALUE].max().to_dict()


def _continuity_streak_days(details: str) -> int:
    m = re.search(r"(\d+)\s+consecutive", details)
    if m:
        return int(m.group(1))
    return 7


def enrich_anomalies(
    df: pd.DataFrame,
    anomalies: list[dict],
    *,
    as_of: pd.Timestamp | None = None,
) -> list[dict]:
    """Add ``impact_score``, ``severity``, and business-impact fields to each record.

    ``severity`` is derived only from ``impact_score`` so the model explains rather
    than invents severity tiers.

    Args:
        df: History window used for detection (for store-level revenue context).
        anomalies: Raw detector output dicts (mutated copies returned).
        as_of: Optional as-of day (reserved for future recency weighting).

    Returns:
        New list of dicts with enrichment fields added.
    """
    _ = as_of  # reserved for recency weighting
    store_rev_max = _store_max_revenue_usd(df)
    out: list[dict] = []

    for raw in anomalies:
        rec = dict(raw)
        store = rec.get("storeid")
        mcode = rec.get("metriccode", "")
        mnorm = _norm_metric_code(mcode)
        issue = rec.get("issue_type", "")
        big_store = float(store_rev_max.get(store, 0.0)) >= _LARGE_STORE_REVENUE

        mv = rec.get("metricvalue")
        if mv is None and "metricvalue" not in rec:
            # Parse from details for negative outlier "metricvalue=-123"
            d = rec.get("details", "")
            m = re.search(r"metricvalue=([+-]?\d+(?:\.\d+)?)", d)
            if m:
                try:
                    mv = float(m.group(1))
                except ValueError:
                    mv = None

        grain_avg = rec.get("grain_lookback_avg_value")
        grain_days = int(rec.get("grain_lookback_distinct_days") or 0)

        # --- impact_score 0..1 ---
        score = 0.35
        if issue == "Negative Outlier":
            score = 0.72
            if mnorm == "REVENUEUSD" and mv is not None:
                score = min(0.95, 0.7 + min(abs(float(mv)) / 25_000.0, 0.25))
            elif mnorm in {"UNITSSOLD", "CUSTCOUNT"}:
                score = 0.68
                if mv is not None:
                    score = min(0.9, 0.65 + min(abs(float(mv)) / 10_000.0, 0.25))
            if big_store:
                score = min(1.0, score + 0.08)
        elif issue == "Positive Spike":
            score = 0.55
            d = rec.get("details", "")
            zm = re.search(r"z=([0-9.]+)", d)
            if zm:
                z = float(zm.group(1))
                score = min(0.85, 0.45 + min(z / 12.0, 0.35))
            if big_store and mnorm in {"REVENUEUSD", "CUSTCOUNT", "UNITSSOLD"}:
                score = min(1.0, score + 0.1)
        elif issue == "Continuity Gap":
            streak = _continuity_streak_days(rec.get("details", ""))
            score = min(0.95, 0.74 + min((streak - 7) / 21.0, 0.2))
            if big_store:
                score = min(1.0, score + 0.05)
        elif issue == "Inconsistent Grain":
            freq = min(grain_days / 7.0, 1.0) if grain_days else 0.0
            vol = 0.0
            if grain_avg is not None and grain_avg == grain_avg:
                vol = min(float(grain_avg) / 8000.0, 0.35)
            score = 0.32 + 0.22 * freq + vol
            if mnorm in {"REVENUEUSD", "CUSTCOUNT", "UNITSSOLD"} and big_store:
                score = min(0.85, score + 0.12)
            if mnorm in {"SYSTEMON", "SYSTEMOFF"}:
                score = min(0.9, score + 0.25)
        score = float(max(0.0, min(1.0, score)))

        rec["impact_score"] = round(score, 4)
        rec["severity"] = severity_from_impact_score(score)

        # --- estimated_revenue_at_risk (heuristic currency units) ---
        rev_risk = 0.0
        if issue == "Negative Outlier" and mnorm == "REVENUEUSD" and mv is not None:
            rev_risk = abs(float(mv))
        elif issue == "Inconsistent Grain" and mnorm == "REVENUEUSD":
            rev_risk = float(grain_avg) if grain_avg is not None else 0.0
        elif issue == "Positive Spike" and mnorm == "REVENUEUSD" and mv is not None:
            rev_risk = max(0.0, float(mv) * 0.01)
        rec["estimated_revenue_at_risk"] = round(rev_risk, 2)

        # --- customer_impact (coarse; for narrative prioritization) ---
        cust = "None"
        if issue == "Continuity Gap":
            cust = "Medium" if big_store else "Low"
        elif mnorm in {"CUSTCOUNT", "REVENUEUSD"}:
            cust = "High" if big_store else "Medium"
        elif mnorm == "UNITSSOLD":
            cust = "Medium" if big_store else "Low"
        elif issue == "Inconsistent Grain":
            cust = "Low"
        rec["customer_impact"] = cust

        # --- operational_risk ---
        op = "Low"
        if issue == "Continuity Gap" or (
            issue == "Inconsistent Grain" and mnorm in {"SYSTEMON", "SYSTEMOFF"}
        ):
            op = "High"
        elif issue in {"Negative Outlier", "Positive Spike"}:
            op = "Medium"
        elif issue == "Inconsistent Grain":
            op = "Medium"
        rec["operational_risk"] = op

        out.append(rec)
    return out
