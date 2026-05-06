"""CLI: run deterministic anomaly detection for a day and summarize with the ADK agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner

from myagent import root_agent
from myagent.anomaly_detector import (
    find_inconsistent_grain,
    find_missing_systemon_streaks,
    find_negative_outliers,
    find_positive_spikes,
    load_metrics,
)
from myagent.anomaly_impact import enrich_anomalies
from myagent.anomaly_to_prompt import format_anomalies_for_llm

DEFAULT_CSV = Path(__file__).resolve().parent / "data" / "retail_data_quality_sim.csv"
DEFAULT_HISTORY_DAYS = 30
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def _parse_as_of_timestamp(date_str: str) -> pd.Timestamp:
    """Parse ``YYYY-MM-DD`` into a timezone-naive midnight Timestamp."""
    return pd.Timestamp(date_str).normalize()


def _filter_history_window(
    df: pd.DataFrame, end: pd.Timestamp, days: int
) -> pd.DataFrame:
    """Keep rows with metricdate in [end - days, end] inclusive."""
    end_ts = end.normalize()
    start_ts = end_ts - timedelta(days=days)
    return df[(df["metricdate"] >= start_ts) & (df["metricdate"] <= end_ts)]


def save_raw_anomalies(
    anomalies: list[dict],
    date_label: str,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Write the combined anomaly list as JSON and CSV under ``output_dir``.

    Creates ``output_dir`` when missing. Filenames use ``raw_anomalies_<date_label>``.

    Args:
        anomalies: Combined detector output (list of plain dicts).
        date_label: Date stem for filenames (typically ``YYYY-MM-DD``).
        output_dir: Destination folder; defaults to project ``output/``.

    Returns:
        Paths ``(json_path, csv_path)`` written.
    """
    root = output_dir if output_dir is not None else OUTPUT_DIR
    root.mkdir(parents=True, exist_ok=True)
    stem = f"raw_anomalies_{date_label}"
    json_path = root / f"{stem}.json"
    csv_path = root / f"{stem}.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(anomalies, f, indent=2, ensure_ascii=False, default=str)

    pd.DataFrame(anomalies).to_csv(csv_path, index=False)

    return json_path, csv_path


def _final_text_from_events(events: list) -> str:
    """Collect human-readable model text from ADK events for one turn."""
    parts: list[str] = []
    for ev in events:
        if ev.author == "user":
            continue
        if not ev.is_final_response():
            continue
        if not ev.content or not ev.content.parts:
            continue
        for part in ev.content.parts:
            t = getattr(part, "text", None)
            if t:
                parts.append(t)
    return "\n".join(parts).strip()


def _apply_top_n_per_store_dept(
    anomalies: list[dict],
    n: int | None,
) -> list[dict]:
    """Keep the top *n* anomalies per (storeid, deptname) by ``impact_score``."""
    if n is None or n <= 0:
        return anomalies
    from collections import defaultdict

    buckets: dict[tuple[object, object], list[dict]] = defaultdict(list)
    for rec in anomalies:
        buckets[(rec.get("storeid"), rec.get("deptname"))].append(rec)
    out: list[dict] = []
    for _key, items in buckets.items():
        ranked = sorted(
            items,
            key=lambda r: -float(r.get("impact_score") or 0.0),
        )
        out.extend(ranked[:n])
    out.sort(
        key=lambda r: (
            {"High": 0, "Medium": 1, "Low": 2}.get(str(r.get("severity")), 2),
            str(r.get("storeid")),
            str(r.get("deptname")),
        )
    )
    return out


def _build_user_prompt(as_of: str, anomaly_block: str) -> str:
    return (
        f"Daily retail data quality review for {as_of}.\n\n"
        "Structured anomaly input follows. Severities, impact scores, and business "
        "hints are **already computed**—explain them; do not replace them with your "
        "own guesses.\n\n"
        f"{anomaly_block}"
    )


async def _run_agent(prompt: str) -> str:
    runner = InMemoryRunner(agent=root_agent, app_name="retail_data_quality_cli")
    session_id = f"run_day_{uuid.uuid4().hex}"
    events = await runner.run_debug(
        prompt,
        quiet=True,
        verbose=False,
        session_id=session_id,
        user_id="run_day_user",
    )
    return _final_text_from_events(events)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Detect retail metric anomalies for a date and summarize with Gemini."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="As-of date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Path to metrics CSV (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=DEFAULT_HISTORY_DAYS,
        help="Days of history ending on --date (default: 30)",
    )
    parser.add_argument(
        "--z-threshold",
        type=float,
        default=4.0,
        help="Z-score threshold for positive spikes",
    )
    parser.add_argument(
        "--grain-min-distinct-days",
        type=int,
        default=3,
        help="Inconsistent grain: min distinct lookback days for a combo (default: 3)",
    )
    parser.add_argument(
        "--grain-min-avg",
        type=float,
        default=None,
        help="Inconsistent grain: min mean metricvalue in lookback (optional)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Per store/dept, only send top N anomalies to the LLM (by impact_score)",
    )
    args = parser.parse_args()

    as_of_ts = _parse_as_of_timestamp(args.date)
    full = load_metrics(str(args.csv))
    window_df = _filter_history_window(full, as_of_ts, args.history_days)

    anomalies: list[dict] = []
    anomalies.extend(find_negative_outliers(window_df))
    anomalies.extend(find_positive_spikes(window_df, z_threshold=args.z_threshold))
    anomalies.extend(find_missing_systemon_streaks(window_df, window_days=7))
    anomalies.extend(
        find_inconsistent_grain(
            window_df,
            lookback_days=7,
            as_of=as_of_ts,
            min_distinct_days=args.grain_min_distinct_days,
            min_avg_value=args.grain_min_avg,
        )
    )

    anomalies = enrich_anomalies(window_df, anomalies, as_of=as_of_ts)
    save_raw_anomalies(anomalies, args.date)

    for_llm = _apply_top_n_per_store_dept(anomalies, args.top_n)
    anomaly_text = format_anomalies_for_llm(for_llm)
    prompt = _build_user_prompt(args.date, anomaly_text)
    result = asyncio.run(_run_agent(prompt))
    print(result)


if __name__ == "__main__":
    main()
