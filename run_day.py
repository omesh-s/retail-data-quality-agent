"""CLI: run deterministic anomaly detection for a day and summarize with the ADK agent."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner

from myagent import root_agent
from myagent.pipeline import DEFAULT_CSV, OUTPUT_DIR, run_detection_pipeline

DEFAULT_HISTORY_DAYS = 30


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

    result = run_detection_pipeline(
        args.csv,
        as_of_date=args.date,
        user_message="",
        history_days=args.history_days,
        z_threshold=args.z_threshold,
        grain_min_distinct_days=args.grain_min_distinct_days,
        grain_min_avg=args.grain_min_avg,
        top_n=args.top_n,
        save_exports=True,
        output_dir=OUTPUT_DIR,
    )

    summary = asyncio.run(_run_agent(result.formatted_prompt))
    print(summary)


if __name__ == "__main__":
    main()
