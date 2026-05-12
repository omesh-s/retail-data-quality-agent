# Lightweight evaluation: detector + enrichment on labeled scenarios.
# python evaluate.py — deterministic only; --with-llm adds Gemini keyword checks (needs API creds).

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
import pandas as pd

from myagent.anomaly_detector import (
    COL_DATE,
    COL_DEPT,
    COL_METRIC,
    COL_STORE,
    COL_VALUE,
    find_inconsistent_grain,
    find_missing_systemon_streaks,
    find_negative_outliers,
    find_positive_spikes,
)
from myagent.anomaly_impact import enrich_anomalies


# One expected detector/enrichment outcome for a test scenario.
@dataclass
class Expectation:
    issue_type: str
    metriccode: str | None = None
    min_severity: str | None = None
    llm_keywords: list[str] = field(default_factory=list)


# Named synthetic window, as-of day, and list of expectations.
@dataclass
class Scenario:
    name: str
    df: pd.DataFrame
    as_of: pd.Timestamp
    expect: list[Expectation]


# Numeric order for comparing severities (High > Medium > Low).
def _severity_rank(s: str) -> int:
    return {"High": 3, "Medium": 2, "Low": 1}.get(s, 0)


# True if rec satisfies expect (issue type, optional metric, min severity).
def _matches(expect: Expectation, rec: dict) -> bool:
    if expect.issue_type != rec.get("issue_type"):
        return False
    if expect.metriccode is not None and expect.metriccode != rec.get("metriccode"):
        return False
    if expect.min_severity is not None:
        if _severity_rank(str(rec.get("severity"))) < _severity_rank(expect.min_severity):
            return False
    return True


# Run all detectors on window_df and return enriched anomaly dicts.
def _run_pipeline(window_df: pd.DataFrame, as_of: pd.Timestamp) -> list[dict]:
    raw: list[dict] = []
    raw.extend(find_negative_outliers(window_df))
    raw.extend(find_positive_spikes(window_df, z_threshold=4.0))
    raw.extend(find_missing_systemon_streaks(window_df, window_days=7))
    raw.extend(
        find_inconsistent_grain(
            window_df,
            lookback_days=7,
            as_of=as_of,
            min_distinct_days=3,
            min_avg_value=None,
        )
    )
    return enrich_anomalies(window_df, raw, as_of=as_of)


# Curated micro-datasets (canonical column names).
def _build_scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = []

    # 1–2: Negative outliers
    scenarios.append(
        Scenario(
            name="negative_revenue",
            df=pd.DataFrame(
                {
                    COL_STORE: [1],
                    COL_DEPT: ["Meat"],
                    COL_METRIC: ["REVENUE_USD"],
                    COL_DATE: pd.to_datetime(["2024-05-20"]),
                    COL_VALUE: [-50.0],
                }
            ),
            as_of=pd.Timestamp("2024-05-20"),
            expect=[
                Expectation(
                    "Negative Outlier",
                    metriccode="REVENUE_USD",
                    min_severity="Medium",
                    llm_keywords=["REVENUE", "Negative"],
                )
            ],
        )
    )
    scenarios.append(
        Scenario(
            name="negative_cust_count",
            df=pd.DataFrame(
                {
                    COL_STORE: [2],
                    COL_DEPT: ["Dairy"],
                    COL_METRIC: ["CUST_COUNT"],
                    COL_DATE: pd.to_datetime(["2024-05-20"]),
                    COL_VALUE: [-1.0],
                }
            ),
            as_of=pd.Timestamp("2024-05-20"),
            expect=[
                Expectation(
                    "Negative Outlier",
                    metriccode="CUST_COUNT",
                    llm_keywords=["CUST", "negative"],
                )
            ],
        )
    )

    # 3: WASTE negative — should NOT fire positive-only rule
    scenarios.append(
        Scenario(
            name="waste_negative_ignored",
            df=pd.DataFrame(
                {
                    COL_STORE: [1],
                    COL_DEPT: ["Grocery"],
                    COL_METRIC: ["WASTE_LBS"],
                    COL_DATE: pd.to_datetime(["2024-05-20"]),
                    COL_VALUE: [-3.0],
                }
            ),
            as_of=pd.Timestamp("2024-05-20"),
            expect=[],
        )
    )

    # 4: Positive spike
    spike_dates = pd.date_range("2024-05-01", periods=25, freq="D")
    spike_vals = [100.0] * 24 + [50_000.0]
    scenarios.append(
        Scenario(
            name="positive_spike",
            df=pd.DataFrame(
                {
                    COL_STORE: [1] * 25,
                    COL_DEPT: ["Bakery"] * 25,
                    COL_METRIC: ["CUST_COUNT"] * 25,
                    COL_DATE: spike_dates,
                    COL_VALUE: spike_vals,
                }
            ),
            as_of=pd.Timestamp("2024-05-25"),
            expect=[
                Expectation(
                    "Positive Spike",
                    metriccode="CUST_COUNT",
                    llm_keywords=["Spike", "CUST"],
                )
            ],
        )
    )

    # 5: Continuity gap — 7-day SYSTEM_ON hole
    rows_c: list[dict] = []
    for d in pd.date_range("2024-05-01", "2024-05-04"):
        rows_c.append(
            {
                COL_STORE: 1,
                COL_DEPT: "Seafood",
                COL_METRIC: "SYSTEM_ON",
                COL_DATE: d,
                COL_VALUE: 1.0,
            }
        )
    for d in pd.date_range("2024-05-05", "2024-05-11"):
        rows_c.append(
            {
                COL_STORE: 1,
                COL_DEPT: "Seafood",
                COL_METRIC: "SYSTEM_ON",
                COL_DATE: d,
                COL_VALUE: float("nan"),
            }
        )
    rows_c.append(
        {
            COL_STORE: 1,
            COL_DEPT: "Seafood",
            COL_METRIC: "SYSTEM_ON",
            COL_DATE: pd.Timestamp("2024-05-12"),
            COL_VALUE: 1.0,
        }
    )
    scenarios.append(
        Scenario(
            name="continuity_gap",
            df=pd.DataFrame(rows_c),
            as_of=pd.Timestamp("2024-05-12"),
            expect=[
                Expectation(
                    "Continuity Gap",
                    metriccode="SYSTEM_ON",
                    min_severity="High",
                    llm_keywords=["continuity", "SYSTEM"],
                )
            ],
        )
    )

    # 6: Inconsistent grain — combo on 3 prior days, missing on as-of; filler on as-of
    g_rows: list[dict] = []
    for d in ["2024-05-17", "2024-05-18", "2024-05-19"]:
        g_rows.append(
            {
                COL_STORE: 4,
                COL_DEPT: "Seafood",
                COL_METRIC: "REVENUE_USD",
                COL_DATE: pd.Timestamp(d),
                COL_VALUE: 5000.0,
            }
        )
    g_rows.append(
        {
            COL_STORE: 4,
            COL_DEPT: "Seafood",
            COL_METRIC: "CUST_COUNT",
            COL_DATE: pd.Timestamp("2024-05-20"),
            COL_VALUE: 100.0,
        }
    )
    scenarios.append(
        Scenario(
            name="inconsistent_grain_revenue",
            df=pd.DataFrame(g_rows),
            as_of=pd.Timestamp("2024-05-20"),
            expect=[
                Expectation(
                    "Inconsistent Grain",
                    metriccode="REVENUE_USD",
                    llm_keywords=["Grain", "Seafood"],
                )
            ],
        )
    )

    # 7: Grain — only 2 distinct days (below min_distinct_days=3) → no hit
    g2: list[dict] = []
    for d in ["2024-05-18", "2024-05-19"]:
        g2.append(
            {
                COL_STORE: 5,
                COL_DEPT: "Deli",
                COL_METRIC: "UNITS_SOLD",
                COL_DATE: pd.Timestamp(d),
                COL_VALUE: 10.0,
            }
        )
    g2.append(
        {
            COL_STORE: 5,
            COL_DEPT: "Deli",
            COL_METRIC: "CUST_COUNT",
            COL_DATE: pd.Timestamp("2024-05-20"),
            COL_VALUE: 50.0,
        }
    )
    scenarios.append(
        Scenario(
            name="grain_not_enough_distinct_days",
            df=pd.DataFrame(g2),
            as_of=pd.Timestamp("2024-05-20"),
            expect=[],
        )
    )

    # 8: min_avg_value filters tiny grain signal
    g3: list[dict] = []
    for d in ["2024-05-17", "2024-05-18", "2024-05-19"]:
        g3.append(
            {
                COL_STORE: 6,
                COL_DEPT: "Meat",
                COL_METRIC: "WASTE_LBS",
                COL_DATE: pd.Timestamp(d),
                COL_VALUE: 0.5,
            }
        )
    g3.append(
        {
            COL_STORE: 6,
            COL_DEPT: "Meat",
            COL_METRIC: "CUST_COUNT",
            COL_DATE: pd.Timestamp("2024-05-20"),
            COL_VALUE: 40.0,
        }
    )
    scenarios.append(
        Scenario(
            name="grain_small_avg_still_flags_without_threshold",
            df=pd.DataFrame(g3),
            as_of=pd.Timestamp("2024-05-20"),
            expect=[
                Expectation("Inconsistent Grain", metriccode="WASTE_LBS"),
            ],
        )
    )

    # 9–10: Severity sanity — negative revenue should be at least Medium
    scenarios.append(
        Scenario(
            name="severity_negative_revenue_highish",
            df=pd.DataFrame(
                {
                    COL_STORE: [9],
                    COL_DEPT: ["Produce"],
                    COL_METRIC: ["REVENUE_USD"],
                    COL_DATE: pd.to_datetime(["2024-06-01"]),
                    COL_VALUE: [-5000.0],
                }
            ),
            as_of=pd.Timestamp("2024-06-01"),
            expect=[
                Expectation("Negative Outlier", metriccode="REVENUE_USD", min_severity="High")
            ],
        )
    )

    # 11: Multiple issue types in one window
    mix: list[dict] = [
        {
            COL_STORE: 7,
            COL_DEPT: "Bakery",
            COL_METRIC: "REVENUE_USD",
            COL_DATE: pd.Timestamp("2024-05-20"),
            COL_VALUE: -10.0,
        },
        {
            COL_STORE: 7,
            COL_DEPT: "Bakery",
            COL_METRIC: "SYSTEM_ON",
            COL_DATE: pd.Timestamp("2024-05-14"),
            COL_VALUE: 1.0,
        },
    ]
    for d in pd.date_range("2024-05-15", "2024-05-21"):
        mix.append(
            {
                COL_STORE: 7,
                COL_DEPT: "Bakery",
                COL_METRIC: "SYSTEM_ON",
                COL_DATE: d,
                COL_VALUE: float("nan"),
            }
        )
    scenarios.append(
        Scenario(
            name="mix_negative_and_continuity",
            df=pd.DataFrame(mix),
            as_of=pd.Timestamp("2024-05-20"),
            expect=[
                Expectation("Negative Outlier", metriccode="REVENUE_USD"),
                Expectation("Continuity Gap"),
            ],
        )
    )

    # 12: Empty frame
    scenarios.append(
        Scenario(
            name="empty_frame",
            df=pd.DataFrame(
                columns=[COL_STORE, COL_DEPT, COL_METRIC, COL_DATE, COL_VALUE]
            ),
            as_of=pd.Timestamp("2024-05-20"),
            expect=[],
        )
    )

    # 13–15: duplicate-style grain / operational flags (smoke)
    scenarios.append(
        Scenario(
            name="grain_system_metric",
            df=pd.DataFrame(
                [
                    {
                        COL_STORE: 8,
                        COL_DEPT: "Grocery",
                        COL_METRIC: "SYSTEM_ON",
                        COL_DATE: pd.Timestamp("2024-05-17"),
                        COL_VALUE: 1.0,
                    },
                    {
                        COL_STORE: 8,
                        COL_DEPT: "Grocery",
                        COL_METRIC: "SYSTEM_ON",
                        COL_DATE: pd.Timestamp("2024-05-18"),
                        COL_VALUE: 1.0,
                    },
                    {
                        COL_STORE: 8,
                        COL_DEPT: "Grocery",
                        COL_METRIC: "SYSTEM_ON",
                        COL_DATE: pd.Timestamp("2024-05-19"),
                        COL_VALUE: 1.0,
                    },
                    {
                        COL_STORE: 8,
                        COL_DEPT: "Grocery",
                        COL_METRIC: "CUST_COUNT",
                        COL_DATE: pd.Timestamp("2024-05-20"),
                        COL_VALUE: 200.0,
                    },
                ]
            ),
            as_of=pd.Timestamp("2024-05-20"),
            expect=[
                Expectation("Inconsistent Grain", metriccode="SYSTEM_ON"),
            ],
        )
    )

    return scenarios


# True if some enriched row matches expect.
def _detector_hits(expect: Expectation, enriched: list[dict]) -> bool:
    return any(_matches(expect, r) for r in enriched)


# True if text contains every keyword (case-insensitive), or no keywords given.
def _llm_mentions(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    low = text.lower()
    return all(kw.lower() in low for kw in keywords)


# Optional Gemini pass: summarize each scenario and check keyword presence.
async def _maybe_llm_eval(scenarios: list[Scenario], enriched_by_name: dict[str, list[dict]]) -> None:
    from google.adk.runners import InMemoryRunner

    from myagent import root_agent
    from myagent.anomaly_to_prompt import format_anomalies_for_llm

    runner = InMemoryRunner(agent=root_agent, app_name="retail_data_quality_eval")
    llm_matched = 0
    llm_total = 0

    for sc in scenarios:
        keyword_sets = [exp.llm_keywords for exp in sc.expect if exp.llm_keywords]
        if not keyword_sets:
            continue
        block = format_anomalies_for_llm(enriched_by_name[sc.name])
        prompt = (
            f"Evaluation run for scenario {sc.name}.\n\n"
            f"{block}\n\n"
            "Summarize anomalies per your instructions."
        )
        events = await runner.run_debug(
            prompt,
            quiet=True,
            verbose=False,
            session_id=f"eval_{sc.name}",
            user_id="eval_user",
        )
        text_parts: list[str] = []
        for ev in events:
            if ev.author == "user":
                continue
            if not ev.is_final_response() or not ev.content:
                continue
            for part in ev.content.parts or []:
                if getattr(part, "text", None):
                    text_parts.append(part.text)
        text = "\n".join(text_parts)
        for kws in keyword_sets:
            llm_total += 1
            if _llm_mentions(text, kws):
                llm_matched += 1
            else:
                print(f"  [LLM] miss: {sc.name} expected keywords {kws}")

    if llm_total:
        print(f"\nLLM keyword checks: {llm_matched}/{llm_total}")


# CLI: run scenario tests; optionally verify LLM summaries mention keywords.
def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate detectors + enrichment (+ optional LLM).")
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Also run Gemini and check keyword overlap (slower; needs credentials).",
    )
    args = parser.parse_args()

    scenarios = _build_scenarios()
    det_ok = 0
    det_total = 0
    enriched_by_name: dict[str, list[dict]] = {}

    # Extra check: min_avg suppresses small grain averages
    df_noise = next(s.df for s in scenarios if s.name == "grain_small_avg_still_flags_without_threshold")
    as_of_noise = next(s.as_of for s in scenarios if s.name == "grain_small_avg_still_flags_without_threshold")
    grain_only = find_inconsistent_grain(
        df_noise,
        lookback_days=7,
        as_of=as_of_noise,
        min_distinct_days=3,
        min_avg_value=10.0,
    )
    if grain_only:
        print("FAIL: grain_min_avg should suppress WASTE_LBS noise when min_avg_value=10")
    else:
        print("OK: grain_min_avg suppresses tiny averages")

    for sc in scenarios:
        enriched = _run_pipeline(sc.df, sc.as_of)
        enriched_by_name[sc.name] = enriched
        if not sc.expect:
            det_total += 1
            if len(enriched) == 0:
                det_ok += 1
            else:
                print(
                    f"FAIL detector: {sc.name} expected no anomalies, got {len(enriched)}"
                )
            continue
        for exp in sc.expect:
            det_total += 1
            if _detector_hits(exp, enriched):
                det_ok += 1
            else:
                print(f"FAIL detector: {sc.name} expected {exp}")

    print(f"\nDetector expectations: {det_ok}/{det_total}")

    if args.with_llm:
        asyncio.run(_maybe_llm_eval(scenarios, enriched_by_name))


# Allow: python evaluate.py [--with-llm]
if __name__ == "__main__":
    main()
