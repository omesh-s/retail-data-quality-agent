"""Deterministic retail metric anomaly detection using pandas."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

import pandas as pd

# Canonical column names after load_metrics()
COL_DEPT = "Deptname"
COL_METRIC = "metriccode"
COL_STORE = "Storeid"
COL_DATE = "metricdate"
COL_VALUE = "metricvalue"

_POSITIVE_ONLY_NORM = frozenset({"UNITSSOLD", "CUSTCOUNT", "REVENUEUSD"})
_SYSTEM_METRIC_NORM = frozenset({"SYSTEMON", "SYSTEMOFF"})


def _norm_metric_code(value: Any) -> str:
    """Uppercase metric code with underscores removed for rule matching."""
    return str(value).replace("_", "").strip().upper()


def load_metrics(csv_path: str) -> pd.DataFrame:
    """Load retail metrics CSV and normalize to canonical column names.

    Accepts simulator headers (Dept_name, metric_code, ...) or already-canonical
    names (Deptname, metriccode, ...).
    """
    df = pd.read_csv(csv_path)
    rename_map: dict[str, str] = {}
    lower_to_actual = {c.lower(): c for c in df.columns}
    pairs = [
        (["deptname", "dept_name"], COL_DEPT),
        (["metriccode", "metric_code"], COL_METRIC),
        (["storeid", "store_id"], COL_STORE),
        (["metricdate", "metric_date"], COL_DATE),
        (["metricvalue", "metric_value"], COL_VALUE),
        (["subdept"], "Subdept"),
    ]
    for candidates, target in pairs:
        for cand in candidates:
            if cand in lower_to_actual:
                src = lower_to_actual[cand]
                if src != target:
                    rename_map[src] = target
                break
    df = df.rename(columns=rename_map)
    df[COL_DATE] = pd.to_datetime(df[COL_DATE], errors="coerce")
    # Coerce metric values: blanks / invalid -> NaN
    df[COL_VALUE] = pd.to_numeric(df[COL_VALUE], errors="coerce")
    return df


def _is_positive_only_metric(metriccode: Any) -> bool:
    return _norm_metric_code(metriccode) in _POSITIVE_ONLY_NORM


def _is_system_metric(metriccode: Any) -> bool:
    return _norm_metric_code(metriccode) in _SYSTEM_METRIC_NORM


def find_negative_outliers(df: pd.DataFrame) -> list[dict]:
    """Flag negative numeric values for metrics that must be non-negative."""
    need = {COL_STORE, COL_DEPT, COL_METRIC, COL_DATE, COL_VALUE}
    missing = need - set(df.columns)
    if missing:
        return []

    out: list[dict] = []
    sub = df[df[COL_VALUE].notna() & (df[COL_VALUE] < 0)].copy()
    sub = sub[sub[COL_METRIC].map(_is_positive_only_metric)]
    for _, row in sub.iterrows():
        out.append(
            {
                "storeid": row[COL_STORE],
                "deptname": row[COL_DEPT],
                "metriccode": row[COL_METRIC],
                "metricvalue": float(row[COL_VALUE]),
                "date_or_range": row[COL_DATE].strftime("%Y-%m-%d"),
                "issue_type": "Negative Outlier",
                "details": (
                    f"metricvalue={row[COL_VALUE]} for positive-only metric "
                    f"{row[COL_METRIC]}"
                ),
            }
        )
    return out


def find_positive_spikes(df: pd.DataFrame, z_threshold: float = 4.0) -> list[dict]:
    """Detect values far above group mean for (Storeid, Deptname, metriccode)."""
    need = {COL_STORE, COL_DEPT, COL_METRIC, COL_DATE, COL_VALUE}
    if need - set(df.columns):
        return []

    out: list[dict] = []
    valid = df[df[COL_VALUE].notna()].copy()
    if valid.empty:
        return out

    grouped = valid.groupby([COL_STORE, COL_DEPT, COL_METRIC], sort=False)
    for (store, dept, mcode), g in grouped:
        vals = g[COL_VALUE].astype(float)
        mean = float(vals.mean())
        std = float(vals.std(ddof=0))
        if std <= 0:
            continue
        z_scores = (vals - mean) / std
        spike_mask = (z_scores > z_threshold) | (vals > mean + 5 * std)
        for _, row in g.loc[spike_mask].iterrows():
            z = float((row[COL_VALUE] - mean) / std)
            out.append(
                {
                    "storeid": store,
                    "deptname": dept,
                    "metriccode": mcode,
                    "metricvalue": float(row[COL_VALUE]),
                    "date_or_range": row[COL_DATE].strftime("%Y-%m-%d"),
                    "issue_type": "Positive Spike",
                    "details": (
                        f"metricvalue={row[COL_VALUE]} vs group mean={mean:.4g}, "
                        f"std={std:.4g}, z={z:.2f} (threshold z>{z_threshold} or "
                        f"value > mean+5*std)"
                    ),
                }
            )
    return out


def find_missing_systemon_streaks(df: pd.DataFrame, window_days: int = 7) -> list[dict]:
    """Find calendar runs of missing SYSTEM_ON / SYSTEM_OFF readings per store+dept.

    A day counts as missing if there is no SYSTEM row for that store+dept on that
    date, or all such rows have null/blank-equivalent metricvalue.
    """
    need = {COL_STORE, COL_DEPT, COL_METRIC, COL_DATE, COL_VALUE}
    if need - set(df.columns):
        return []

    sys_df = df[df[COL_METRIC].map(_is_system_metric)].copy()
    if sys_df.empty:
        return []

    d_min = df[COL_DATE].min()
    d_max = df[COL_DATE].max()
    if pd.isna(d_min) or pd.isna(d_max):
        return []

    def day_valid(store: Any, dept: Any, day: pd.Timestamp) -> bool:
        rows = sys_df[
            (sys_df[COL_STORE] == store)
            & (sys_df[COL_DEPT] == dept)
            & (sys_df[COL_DATE].dt.normalize() == day.normalize())
        ]
        if rows.empty:
            return False
        return bool(rows[COL_VALUE].notna().any())

    out: list[dict] = []
    pairs_list = list(
        sys_df[[COL_STORE, COL_DEPT]].drop_duplicates().itertuples(index=False, name=None)
    )
    end = d_max.normalize()

    for store, dept in pairs_list:
        streak_start: pd.Timestamp | None = None
        streak_len = 0
        cur = d_min.normalize()
        while cur <= end:
            ok = day_valid(store, dept, cur)
            if not ok:
                if streak_start is None:
                    streak_start = cur
                streak_len += 1
            else:
                if streak_len >= window_days and streak_start is not None:
                    last = cur - timedelta(days=1)
                    out.append(
                        {
                            "storeid": store,
                            "deptname": dept,
                            "metriccode": "SYSTEM_ON",
                            "date_or_range": (
                                f"{streak_start.strftime('%Y-%m-%d')} to "
                                f"{last.strftime('%Y-%m-%d')}"
                            ),
                            "issue_type": "Continuity Gap",
                            "details": (
                                f"{streak_len} consecutive calendar days with missing "
                                f"SYSTEM_ON/SYSTEM_OFF value in window"
                            ),
                        }
                    )
                streak_start = None
                streak_len = 0
            cur += timedelta(days=1)
        if streak_len >= window_days and streak_start is not None:
            last = end
            out.append(
                {
                    "storeid": store,
                    "deptname": dept,
                    "metriccode": "SYSTEM_ON",
                    "date_or_range": (
                        f"{streak_start.strftime('%Y-%m-%d')} to "
                        f"{last.strftime('%Y-%m-%d')}"
                    ),
                    "issue_type": "Continuity Gap",
                    "details": (
                        f"{streak_len} consecutive calendar days with missing "
                        f"SYSTEM_ON/SYSTEM_OFF value in window"
                    ),
                }
            )

    return out


def find_inconsistent_grain(
    df: pd.DataFrame,
    lookback_days: int = 7,
    as_of: pd.Timestamp | None = None,
    min_distinct_days: int = 3,
    min_avg_value: float | None = None,
) -> list[dict]:
    """Flag missing (Deptname, metriccode) combos on the reference day versus recent history.

    Compares rows on the reference calendar day to the union of combos seen on each
    of the ``lookback_days`` immediately prior days for the same store.

    Args:
        df: Metrics dataframe with canonical columns (see ``load_metrics``).
        lookback_days: Number of calendar days before the reference day to scan.
        as_of: Reference calendar day (normalized). If ``None``, uses the latest
            ``metricdate`` present in *df* (previous behavior).
        min_distinct_days: Only flag if the combo appeared on at least this many
            distinct calendar days in the lookback window.
        min_avg_value: When set, only flag if the mean ``metricvalue`` over
            lookback rows for that combo is >= this threshold (filters tiny/noisy
            metrics). Requires ``metricvalue`` column.

    Returns:
        Anomaly dicts with ``issue_type`` ``Inconsistent Grain``. Requires at least
        one row for each store on the reference day so expectations are grounded.
    """
    need = {COL_STORE, COL_DEPT, COL_METRIC, COL_DATE}
    if need - set(df.columns):
        return []

    if min_avg_value is not None and COL_VALUE not in df.columns:
        return []

    if df.empty:
        return []

    if as_of is not None:
        reference_day = pd.Timestamp(as_of).normalize()
        if pd.isna(reference_day):
            return []
    else:
        d_max = df[COL_DATE].max()
        if pd.isna(d_max):
            return []
        reference_day = d_max.normalize()

    out: list[dict] = []

    for store, g_store in df.groupby(COL_STORE, sort=False):
        present_rows = g_store[g_store[COL_DATE].dt.normalize() == reference_day]
        if present_rows.empty:
            continue
        present = set(zip(present_rows[COL_DEPT], present_rows[COL_METRIC]))

        combo_dates: dict[tuple[Any, Any], set[pd.Timestamp]] = defaultdict(set)
        combo_values: dict[tuple[Any, Any], list[float]] = defaultdict(list)

        for offset in range(1, lookback_days + 1):
            d_ref = reference_day - timedelta(days=offset)
            day_rows = g_store[g_store[COL_DATE].dt.normalize() == d_ref]
            for _, r in day_rows.iterrows():
                combo = (r[COL_DEPT], r[COL_METRIC])
                combo_dates[combo].add(d_ref.normalize())
                if COL_VALUE in r.index and pd.notna(r[COL_VALUE]):
                    combo_values[combo].append(float(r[COL_VALUE]))

        for combo, dates in combo_dates.items():
            if combo in present:
                continue
            n_distinct = len(dates)
            if n_distinct < min_distinct_days:
                continue

            vals = combo_values.get(combo, [])
            avg_val: float | None
            if vals:
                avg_val = float(sum(vals) / len(vals))
            else:
                avg_val = None

            if min_avg_value is not None:
                if avg_val is None or avg_val < min_avg_value:
                    continue

            dept, mcode = combo
            out.append(
                {
                    "storeid": store,
                    "deptname": dept,
                    "metriccode": mcode,
                    "date_or_range": reference_day.strftime("%Y-%m-%d"),
                    "issue_type": "Inconsistent Grain",
                    "grain_lookback_distinct_days": n_distinct,
                    "grain_lookback_avg_value": avg_val,
                    "details": (
                        f"combo absent on as-of date but appeared on "
                        f"{n_distinct} distinct day(s) in prior {lookback_days}-day lookback"
                        + (
                            f"; lookback avg metricvalue={avg_val:.4g}"
                            if avg_val is not None
                            else ""
                        )
                    ),
                }
            )
    return out
