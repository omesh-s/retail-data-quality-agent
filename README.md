# Retail Data Quality Agent

A retail data quality agent that detects anomalies in daily store metrics and summarizes them through both a CLI and a browser-based ADK chat interface. It runs **deterministic Python checks** (pandas) for continuity gaps, positive spikes, negative outliers, and inconsistent grain, then scores and groups results. A **Google ADK + Gemini** model turns that structured output into short summaries.

You can use the project in three complementary ways:

- **CLI** — `run_day.py` for a given date (prints a summary to the terminal).
- **Browser (ADK)** — `adk web .` opens the ADK chat UI; the agent calls the **same live pipeline** as the CLI via an ADK tool (not a hardcoded sample payload).
- **HTTP companion** — optional FastAPI app (`app/main.py`) with a **`/health`** probe and room to grow (orchestration, internal tools). Default bind is **`127.0.0.1:8080`** so it does not collide with ADK Web’s usual **`:8000`** port.

## Problem statement

Daily metrics (store, department, metric code) need monitoring: missing system indicators, impossible negatives on volume-style metrics, suspicious spikes, and **grain** issues (expected store / department / metric combinations missing on a day when history suggests they should appear). Raw rule hits are noisy; **severity** should come from code (`impact_score`, High/Medium/Low), not from the model guessing.

The stack is: **detect → enrich → optional top‑N for the LLM → format for the model → Gemini explains** using only the supplied facts.

## Prerequisites

- **Python** 3.11+ (tested on 3.13).
- **Dependencies**: `pip install -r requirements.txt` (core agent stack plus `fastapi`, `uvicorn`, `pydantic-settings`, `pyyaml` for the HTTP layer and config).
- **Configuration**: copy `.env.example` to `.env` and adjust; never commit secrets.
- **Gemini credentials** (e.g. in `.env`) for any path that calls the model: `run_day.py`, `adk web`, and `evaluate.py --with-llm`. **`evaluate.py` alone** does not call the LLM by default.

## Quick start

Create a virtual environment and install dependencies.

**Windows (PowerShell or cmd)**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then:

```bash
python evaluate.py
python run_day.py --date 2024-05-20 --grain-min-avg 100 --top-n 5
```

- `evaluate.py` — deterministic scenario checks only (no Gemini unless you pass `--with-llm`).
- `run_day.py` — runs the full pipeline and prints a summary; **requires** Gemini (or equivalent) configuration.

**Configuration (shared defaults)** — `config/settings.py` loads environment variables (see `.env.example`). CLI flags override those defaults. The ADK tool (`myagent/retail_tool.py`) reads the same settings for pipeline parameters and CSV path.

## Results

- Deterministic evaluation: **13/13** scenario checks passed (`python evaluate.py`).
- **CLI and ADK web chat share the same backend**: `myagent/pipeline.py` (`run_detection_pipeline`). For the same date and settings, both consume the same detector and enrichment output; the written summary may differ slightly per model run, but it is grounded in the same anomaly list and severities.
- The **FastAPI companion** reuses **`config/settings.py`** for service/logging defaults only; it does not fork detection logic. Adding HTTP-triggered pipeline calls later would call `run_detection_pipeline` explicitly—same as today.

## Architecture

Shared **detection pipeline** (CSV → window → rules → `enrich_anomalies` → save raw exports → `format_anomalies_for_llm`):

```text
                    ┌─────────────────────┐
                    │ retail CSV          │
                    │ (daily metrics)     │
                    └──────────┬──────────┘
                               │ load_metrics()
                               ▼
                    ┌─────────────────────┐
                    │ History window      │
                    │ (e.g. 30d to as-of) │
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
     output/raw_*.json   optional top-N     format_anomalies_for_llm()
     output/raw_*.csv     (LLM subset)       (grouped by store/dept)
                               │
         ┌─────────────────────┴─────────────────────┐
         ▼                                           ▼
  run_day.py → InMemoryRunner                  adk web → root_agent
  (CLI, prints summary)                        calls tool → same pipeline
                                               then Gemini summarizes

  uvicorn app.main:app                         (optional) /health + future routes;
  (127.0.0.1:8080 by default)                  does not replace ADK Web or the pipeline
```

**Entry points**

| Path | What it does |
|------|----------------|
| **`run_day.py`** | Thin CLI: calls `run_detection_pipeline` in `myagent/pipeline.py`, then runs the root agent on the formatted prompt (stdout). |
| **`adk web .`** | Web UI: user chats with `root_agent` in `myagent/agent.py`. The agent invokes **`run_retail_data_quality_analysis`** (`myagent/retail_tool.py`), which calls the **same** `run_detection_pipeline`. |
| **`uvicorn app.main:app`** | Small FastAPI service: **`GET /health`**, structured logging hooks, Pydantic response schemas. Complements CLI/ADK; anomaly logic stays in `myagent/`. |

There is **no** separate fake anomaly payload for the web: CLI and ADK both execute the real detectors and enrichment on your CSV. The FastAPI app is a **sidecar** for probes and future HTTP integration, not a second pipeline.

## How to run `evaluate.py`

Labeled micro-scenarios for detectors + enrichment (default: **no** LLM):

```bash
python evaluate.py
```

Expect: `Detector expectations: 13/13` and a check that optional grain `min_avg_value` filtering behaves as expected.

Optional LLM keyword smoke test (slower, needs credentials):

```bash
python evaluate.py --with-llm
```

## How to run `run_day.py` (CLI)

Analyze one calendar day against the metrics CSV, write raw artifacts under `output/`, and print a Gemini summary:

```bash
python run_day.py --date 2024-05-20
```

| Flag | Purpose |
|------|---------|
| `--csv PATH` | Alternate metrics file |
| `--history-days N` | Lookback ending on `--date` (default from env / `30`) |
| `--z-threshold` | Positive spike z-score threshold (default from env / `4.0`) |
| `--grain-min-distinct-days` | Min distinct lookback days for inconsistent grain (default from env / `3`) |
| `--grain-min-avg` | Optional min mean `metricvalue` in lookback for grain (default from env) |
| `--top-n` | Per store/dept, cap anomalies **sent to the LLM** by `impact_score` (full enriched list still saved; default from env) |

Artifacts:

- `output/raw_anomalies_<YYYY-MM-DD>.json`
- `output/raw_anomalies_<YYYY-MM-DD>.csv`

## Companion HTTP API (FastAPI)

Optional service for **health checks** and future operational endpoints. It does **not** host the ADK chat UI and does **not** duplicate anomaly logic.

From the **project root**:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

Or:

```bash
python -m app.main
```

Smoke test:

```bash
curl -s http://127.0.0.1:8080/health
```

**Logging**

- Default: readable console lines (`LOG_FORMAT=console`, `LOG_LEVEL=INFO`).
- Set `LOG_FORMAT=json` for one-line JSON records (no extra dependencies).
- Or set `LOG_CONFIG_FILE` to a YAML `dictConfig`, e.g. `config/logging/text.yaml`, `config/logging/json_dev.yaml`, `config/logging/json_prod.yaml`.

**Docker** (API process only; mount data and `.env` as needed):

```bash
docker build -t retail-dq .
docker run -p 8080:8080 --env-file .env retail-dq
```

## Web UI (ADK Chat)

From the **project root** (the folder that **contains** the `myagent` directory), run:

```bash
adk web .
```

1. Open the URL shown in the terminal (default `http://127.0.0.1:8000`).
2. Select the **`myagent`** app.
3. Ask something concrete, for example:  
   **“Analyze retail data quality issues for 2024-05-20 and summarize the most severe anomalies by store and department.”**

The chat agent **must** call the **`run_retail_data_quality_analysis`** tool. That runs **`run_detection_pipeline`** — the same code path as **`run_day.py`** (detectors, `enrich_anomalies`, `format_anomalies_for_llm`, raw exports). It is **not** a hardcoded sample list.

- If the user gives a **`YYYY-MM-DD`** in the message (or the model passes it as `as_of_date`), that day is used; otherwise the tool falls back to the **latest** `metricdate` in the CSV.
- Each analysis that hits the tool can **refresh** `output/raw_anomalies_<date>.json` and `.csv` for that resolved as-of date.

Pipeline-related environment variables are centralized in **`config/settings.py`** / **`.env.example`** (`RETAIL_METRICS_CSV`, `RETAIL_HISTORY_DAYS`, `RETAIL_Z_THRESHOLD`, `RETAIL_GRAIN_MIN_DISTINCT`, `RETAIL_GRAIN_MIN_AVG`, `RETAIL_TOP_N`, plus `SERVICE_HOST`, `SERVICE_PORT`, logging keys).

## Example output snippets (2024-05-20)

### Raw detector + enrichment (CSV)

First rows of `output/raw_anomalies_2024-05-20.csv` (ellipsis in the header row; open the file for all columns):

```text
storeid,deptname,metriccode,metricvalue,date_or_range,issue_type,...,impact_score,severity,estimated_revenue_at_risk,customer_impact,operational_risk,...
4,Dairy,UNITS_SOLD,-999999.0,2024-04-30,Negative Outlier,...,0.98,High,0.0,Medium,Medium,...
2,Produce,SYSTEM_ON,,2024-05-02 to 2024-05-20,Continuity Gap,...,0.99,High,0.0,Medium,High,...
4,Seafood,SYSTEM_ON,,2024-04-30 to 2024-05-06,Continuity Gap,...,0.79,High,0.0,Medium,High,...
```

### LLM summary (stdout)

Excerpt from `python run_day.py --date 2024-05-20 --grain-min-avg 100 --top-n 5` (wording varies by run):

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

## Project layout

| Path | Role |
|------|------|
| `myagent/pipeline.py` | **Core pipeline** — `run_detection_pipeline`: CSV window, detectors, enrichment, `output/raw_*`, formatted prompt. **Source of truth** for batch analysis. |
| `myagent/retail_tool.py` | **ADK tool** — `run_retail_data_quality_analysis`; uses `config/settings.py` and the shared pipeline for **`adk web`**. |
| `myagent/agent.py` | **Agent** — `root_agent`, tool registration, summarization instructions. |
| `run_day.py` | **CLI entry** — pipeline + `InMemoryRunner` + stdout; argparse defaults from settings / `.env`. |
| `evaluate.py` | **Eval entry** — scenario checks on detectors + enrichment (optional `--with-llm`). |
| `myagent/anomaly_detector.py` | **Detection** — `load_metrics`, `find_*` rule functions. |
| `myagent/anomaly_impact.py` | **Enrichment** — `enrich_anomalies`. |
| `myagent/anomaly_to_prompt.py` | **Prompt shaping** — `format_anomalies_for_llm`. |
| `config/settings.py` | **Settings** — env-driven defaults (HTTP bind, logging, `RETAIL_*`). |
| `config/logging/*.yaml` | **Logging** — optional `dictConfig` files for console / JSON. |
| `app/main.py` | **HTTP service** — FastAPI app, `/health`, validation error schema. |
| `app/schemas/responses.py` | **API schemas** — `HealthResponse`, `MessageResponse`, `ErrorResponse`. |
| `app/logging_setup.py` | **Logging bootstrap** — YAML or inline console/JSON. |
| `Dockerfile` | **Container** — runs `uvicorn` (API); use host `adk web` for chat during dev. |
| `.env.example` | **Safe template** — copy to `.env`; no secrets committed. |
| `data/` | Sample retail metrics CSV (`retail_data_quality_sim.csv`). |
