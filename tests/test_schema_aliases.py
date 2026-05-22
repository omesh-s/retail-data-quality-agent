"""Column alias normalization."""

from __future__ import annotations

import pandas as pd
import pytest

from config.schema_aliases import (
    apply_schema_normalization,
    build_column_rename_map,
)


def test_maps_common_variants():
    raw = pd.DataFrame(
        {
            "location_id": [1],
            "department_name": ["Dairy"],
            "kpi_code": ["UNITS_SOLD"],
            "business_date": ["2024-05-20"],
            "amount": [9.0],
        }
    )
    out = apply_schema_normalization(raw)
    assert list(out.columns) == [
        "Storeid",
        "Deptname",
        "metriccode",
        "metricdate",
        "metricvalue",
    ]


def test_missing_required_raises():
    raw = pd.DataFrame({"date": ["2024-05-20"], "value": [1.0]})
    with pytest.raises(ValueError, match="missing required"):
        apply_schema_normalization(raw)


def test_custom_map_file(tmp_path):
    map_path = tmp_path / "map.json"
    map_path.write_text('{"loc": "Storeid"}', encoding="utf-8")
    raw = pd.DataFrame(
        {
            "loc": [2],
            "deptname": ["Meat"],
            "metric_code": ["REVENUE_USD"],
            "metric_date": ["2024-05-20"],
            "metric_value": [1.0],
        }
    )
    report = build_column_rename_map(list(raw.columns), map_file=map_path)
    assert report.rename_map.get("loc") == "Storeid"
