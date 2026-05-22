"""Lightweight checks for large-frame normalization."""

from __future__ import annotations

import pandas as pd

from config.schema_aliases import apply_schema_normalization


def test_large_frame_normalization():
    n = 50_000
    raw = pd.DataFrame(
        {
            "store_id": (i % 50 for i in range(n)),
            "department": ["Dairy"] * n,
            "metric_code": ["UNITS_SOLD"] * n,
            "business_date": pd.date_range("2024-01-01", periods=n, freq="h"),
            "metric_value": 1.0,
        }
    )
    out = apply_schema_normalization(raw)
    assert len(out) == n
    assert "metricdate" in out.columns
    assert out["Deptname"].nunique() == 1
