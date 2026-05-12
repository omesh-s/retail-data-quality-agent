# CLI: run detection for a day and summarize with the ADK/Gemini agent.

from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner

from config.settings import get_settings
from myagent import root_agent
from myagent.pipeline import DEFAULT_CSV, OUTPUT_DIR, run_detection_pipeline


# Collect human-readable model text from ADK events for one turn.
def _final_text_from_events(events: list) -> str:
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


# Send prompt to the ADK agent and return the final model text.
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


# Parse CLI args, run the detection pipeline, print the Gemini summary.
def main() -> None:
    load_dotenv()
    get_settings.cache_clear()
    s = get_settings()

    default_csv = s.retail_metrics_csv or DEFAULT_CSV

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
        default=default_csv,
        help=f"Path to metrics CSV (default: from RETAIL_METRICS_CSV or {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=s.retail_history_days,
        help="Days of history ending on --date",
    )
    parser.add_argument(
        "--z-threshold",
        type=float,
        default=s.retail_z_threshold,
        help="Z-score threshold for positive spikes",
    )
    parser.add_argument(
        "--grain-min-distinct-days",
        type=int,
        default=s.retail_grain_min_distinct,
        help="Inconsistent grain: min distinct lookback days for a combo",
    )
    parser.add_argument(
        "--grain-min-avg",
        type=float,
        default=s.retail_grain_min_avg,
        help="Inconsistent grain: min mean metricvalue in lookback (optional)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=s.retail_top_n,
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


# Allow: python run_day.py --date ...
if __name__ == "__main__":
    main()
