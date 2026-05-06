# Retail Data Quality Agent

A hybrid retail anomaly detection system that combines deterministic Python checks with a Google ADK + Gemini agent to generate executive-ready data quality summaries.

Built to detect continuity gaps, spikes, negative outliers, and inconsistent grain in daily aggregated store metrics.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python evaluate.py
python run_day.py --date 2024-05-20 --grain-min-avg 100 --top-n 5
```

On macOS or Linux, activate the venv with `source .venv/bin/activate`. Configure Gemini credentials (for example `.env`) before `run_day.py` if you want the LLM summary; `evaluate.py` alone does not require an API call.

## Results

- Deterministic detector evaluation: **13/13** scenario checks passed.
- End-to-end runs generate:
  - raw anomaly exports in JSON and CSV
  - grouped store/department summaries
  - severity-aware Gemini narratives with operational and revenue-risk context

## Problem statement

Daily retail metrics (by store, department, and metric code) need consistent monitoring: missing system indicators, impossible negative volumes, suspicious spikes, and incomplete “grain” (expected store / department / metric combinations that disappear on a given day). Raw rule hits are too noisy for executives, and severity should not be invented by a language model alone.

This project combines:

- **Deterministic detection** in Python (pandas) over CSV extracts.
- **Scoring and business hints** (`impact_score`, High/Medium/Low `severity`, revenue-at-risk and operational-risk fields).
- **A Google ADK + Gemini agent** that explains and groups issues using only the structured facts you pass in—not ad‑hoc severity.

The goal is decision-ready summaries: fewer false alarms, explicit severity, and narratives aligned with store and department ownership.

## Architecture

Data and control flow:

```text
                    ┌─────────────────────┐
                    │ retail CSV          │
                    │ (daily metrics)     │
                    └──────────┬──────────┘
                               │ load_metrics()
                               ▼
                    ┌─────────────────────┐
                    │ History window      │
                    │ (e.g. 30d to --date)│
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
  find_negative_*      find_positive_*      find_missing_*
  find_inconsistent_*  (grain thresholds)   systemon_streaks
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │ combined list[dict]
                               ▼
                    ┌─────────────────────┐
                    │ enrich_anomalies()  │
                    │ severity, impact,   │
                    │ revenue/cust/ops    │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     output/raw_*.json   optional --top-n   format_anomalies_for_llm()
     output/raw_*.csv     (LLM subset only)  (grouped by store/dept)
                               │
                               ▼
                    ┌─────────────────────┐
                    │ ADK InMemoryRunner  │
                    │ root_agent (Gemini) │
                    └──────────┬──────────┘
                               ▼
                    Summary + Anomalies Found
                    (stdout / demo)
```

Conceptually: **detectors → enrichment → persistence → prompt shaping → LLM**. The agent does not replace rules; it interprets and groups what the pipeline already labeled.

## Prerequisites

- Python 3.11+ (project tested with 3.13).
- Virtual environment with dependencies from `requirements.txt` (`google-adk`, `google-genai`, `pandas`, `python-dotenv`, …).
- API credentials for Gemini (for example via `.env` and your usual Google GenAI / Vertex setup—match what you already use for `adk web`).

## How to run `evaluate.py`

Deterministic checks on labeled micro-scenarios (no LLM by default):

```bash
python evaluate.py
```

You should see a line such as `Detector expectations: 13/13` plus a check that optional grain `min_avg_value` filtering behaves as expected.

Optional: also run the agent once per scenario and score simple keyword overlap (slower; needs credentials):

```bash
python evaluate.py --with-llm
```

## How to run `run_day.py`

Analyze a calendar day against the default simulator CSV, write raw anomaly artifacts, then print the Gemini summary:

```bash
python run_day.py --date 2024-05-20
```

Useful flags:

| Flag | Purpose |
|------|---------|
| `--csv PATH` | Alternate metrics file |
| `--history-days N` | Lookback window length ending on `--date` (default 30) |
| `--z-threshold` | Positive spike z-score threshold (default 4.0) |
| `--grain-min-distinct-days` | Minimum distinct lookback days for inconsistent grain (default 3) |
| `--grain-min-avg` | Optional minimum mean `metricvalue` in lookback to flag grain |
| `--top-n` | Per store/dept, only the top N anomalies by `impact_score` are sent to the LLM (full list still saved under `output/`) |

Artifacts:

- `output/raw_anomalies_<YYYY-MM-DD>.json`
- `output/raw_anomalies_<YYYY-MM-DD>.csv`

## Example output snippets (2024-05-20)

### Raw detector + enrichment (CSV)

First rows of `output/raw_anomalies_2024-05-20.csv` (columns truncated in prose; see file for full width):

```text
storeid,deptname,metriccode,metricvalue,date_or_range,issue_type,...,impact_score,severity,estimated_revenue_at_risk,customer_impact,operational_risk,...
4,Dairy,UNITS_SOLD,-999999.0,2024-04-30,Negative Outlier,...,0.98,High,0.0,Medium,Medium,...
2,Produce,SYSTEM_ON,,2024-05-02 to 2024-05-20,Continuity Gap,...,0.99,High,0.0,Medium,High,...
4,Seafood,SYSTEM_ON,,2024-04-30 to 2024-05-06,Continuity Gap,...,0.79,High,0.0,Medium,High,...
```

### LLM summary (stdout)

Example excerpt from `python run_day.py --date 2024-05-20 --grain-min-avg 100 --top-n 5` (wording varies slightly per model run):

```text
Summary:
-   **Overall Health Score: Critical**
-   **Short Assessment:** The data quality for 2024-05-20 is critically impacted by widespread High and Medium severity anomalies across multiple stores and departments. Key issues include numerous "Continuity Gaps" for `SYSTEM_ON` data, indicating potential operational data capture failures with high operational risk. Additionally, "Inconsistent Grain" for `REVENUE_USD` is prevalent, affecting multiple departments and leading to an estimated revenue at risk of over $40,000 across the highlighted instances. Several critical "Negative Outliers" for `UNITS_SOLD` and `CUST_COUNT` also point to data corruption affecting important retail metrics.

Anomalies Found:

**Store 1**
*   **Dairy (2 High):** Includes a High severity "Continuity Gap" for `SYSTEM_ON` (9 days, High operational risk) and a High severity "Inconsistent Grain" for `REVENUE_USD` on 2024-05-20, indicating an estimated revenue at risk of $5,038.53.
*   **Grocery (1 High, 2 Medium):** Features a High severity "Continuity Gap" for `SYSTEM_ON` (7 days, High operational risk). Additionally, there are Medium severity "Inconsistent Grain" issues for `CUST_COUNT` and `UNITS_SOLD` on 2024-05-20, impacting customer and operational visibility.
*   ...
```

## Project layout (high level)

| Path | Role |
|------|------|
| `myagent/agent.py` | ADK `root_agent` instruction |
| `myagent/anomaly_detector.py` | Load CSV, detection functions |
| `myagent/anomaly_impact.py` | `enrich_anomalies` (severity, scores, business hints) |
| `myagent/anomaly_to_prompt.py` | Grouped prompt text for the LLM |
| `run_day.py` | CLI entry |
| `evaluate.py` | Scenario-based evaluation |
| `data/` | Sample retail metrics CSV |
