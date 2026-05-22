"""Map variant retail metric column names to canonical pipeline columns."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from myagent.anomaly_detector import (
    COL_DATE,
    COL_DEPT,
    COL_METRIC,
    COL_STORE,
    COL_VALUE,
)

logger = logging.getLogger(__name__)

OPTIONAL_CANONICAL = {"Subdept": "subdept"}


def _normalize_key(name: str) -> str:
    return "".join(ch for ch in str(name).strip().lower() if ch.isalnum())


# Built-in aliases: normalized key -> canonical column name.
RETAIL_DEFAULT_ALIASES: dict[str, str] = {}
for _canonical, _variants in {
    COL_STORE: [
        "storeid",
        "store_id",
        "store",
        "location_id",
        "locationid",
        "loc_id",
    ],
    COL_DEPT: [
        "deptname",
        "dept_name",
        "department",
        "dept",
        "department_name",
        "departmentname",
    ],
    COL_METRIC: [
        "metriccode",
        "metric_code",
        "metric",
        "metric_name",
        "metricname",
        "kpi",
        "kpi_code",
    ],
    COL_DATE: [
        "metricdate",
        "metric_date",
        "date",
        "business_date",
        "report_date",
        "day",
    ],
    COL_VALUE: [
        "metricvalue",
        "metric_value",
        "value",
        "amount",
        "metric_val",
    ],
    "Subdept": ["subdept", "sub_dept", "subdepartment", "sub_department"],
}.items():
    for v in _variants:
        RETAIL_DEFAULT_ALIASES[_normalize_key(v)] = _canonical
    RETAIL_DEFAULT_ALIASES[_normalize_key(_canonical)] = _canonical


REQUIRED_CANONICAL = (COL_STORE, COL_DEPT, COL_METRIC, COL_DATE)


@dataclass(frozen=True)
class SchemaMappingReport:
    """Result of column resolution for logging and errors."""

    rename_map: dict[str, str]
    unmapped_input_columns: list[str]
    missing_required: list[str]

    @property
    def ok(self) -> bool:
        return not self.missing_required


def load_alias_overrides(path: Path | None) -> dict[str, str]:
    """Load JSON map of normalized_input_key -> canonical column name."""
    if path is None or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Schema map file must be a JSON object: {path}")
    out: dict[str, str] = {}
    for raw_key, canonical in data.items():
        out[_normalize_key(str(raw_key))] = str(canonical)
    return out


def build_column_rename_map(
    columns: list[str],
    *,
    profile: str = "retail_default",
    map_file: Path | None = None,
) -> SchemaMappingReport:
    """Resolve *columns* to canonical names using built-in and optional overrides."""
    alias_table = dict(RETAIL_DEFAULT_ALIASES)
    if map_file:
        alias_table.update(load_alias_overrides(map_file))
    elif profile != "retail_default":
        logger.debug("Unknown schema profile %s; using retail_default aliases", profile)

    rename: dict[str, str] = {}
    used_canonical: set[str] = set()
    unmapped: list[str] = []

    for col in columns:
        key = _normalize_key(col)
        target = alias_table.get(key)
        if target is None:
            unmapped.append(col)
            continue
        if col == target:
            used_canonical.add(target)
            continue
        if target in used_canonical:
            logger.warning(
                "Column %r maps to %s but %s already assigned; keeping first match",
                col,
                target,
                target,
            )
            continue
        rename[col] = target
        used_canonical.add(target)

    missing = [c for c in REQUIRED_CANONICAL if c not in used_canonical and c not in columns]
    return SchemaMappingReport(
        rename_map=rename,
        unmapped_input_columns=unmapped,
        missing_required=missing,
    )


def apply_schema_normalization(
    df: pd.DataFrame,
    *,
    profile: str = "retail_default",
    map_file: Path | None = None,
) -> pd.DataFrame:
    """Rename columns, coerce types, and apply light dtypes for large frames."""
    report = build_column_rename_map(list(df.columns), profile=profile, map_file=map_file)
    if report.rename_map:
        logger.info(
            "Schema mapping: %s",
            ", ".join(f"{k!r}->{v}" for k, v in sorted(report.rename_map.items())),
        )
    if report.unmapped_input_columns:
        logger.debug("Unmapped columns (kept as-is): %s", report.unmapped_input_columns)
    if report.missing_required:
        raise ValueError(
            "Metrics data missing required columns after alias mapping. "
            f"Missing: {report.missing_required}. "
            f"Input columns: {list(df.columns)}. "
            "Set DATA_SCHEMA_MAP_FILE or fix source column names."
        )

    out = df.rename(columns=report.rename_map)
    if COL_DATE not in out.columns:
        raise ValueError(
            f"Metrics data missing date column; got: {list(out.columns)}"
        )

    out[COL_DATE] = pd.to_datetime(out[COL_DATE], errors="coerce")
    if COL_VALUE in out.columns:
        out[COL_VALUE] = pd.to_numeric(out[COL_VALUE], errors="coerce")

    for col in (COL_STORE, COL_DEPT, COL_METRIC):
        if col in out.columns and out[col].dtype == object:
            nunique = out[col].nunique(dropna=True)
            if nunique > 0 and len(out) > 10_000 and nunique < len(out) // 2:
                out[col] = out[col].astype("category")

    return out
