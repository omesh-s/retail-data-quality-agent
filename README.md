# Retail Data Quality Agent

Monitors daily retail store metrics with **deterministic pandas rules** (continuity gaps, spikes, negative outliers, inconsistent grain), then enriches hits with severity and impact scores. Optional **Google ADK + Gemini** turns structured findings into short summaries for CLI and chat.

**What it does**

- One **shared anomaly pipeline** (`myagent/pipeline.py`) — source of truth for detection and enrichment
- **CLI + ADK web** use the same provider-backed backend (`run_anomaly_pipeline`)
- **Daily report** — top issues + optional **Slack** (no LLM)
- **Optional HTTP companion** — health probe and daily-report trigger (not the chat UI)
- **Pluggable data sources** — `local_csv` (default) or `databricks_mcp` (HTTP JSON-RPC)

**Requirements:** Python 3.11+ (tested on 3.13). Copy `.env.example` → `.env`. Gemini credentials are required for `run_day.py`, `adk web`, and `evaluate.py --with-llm` only.

## Quick start

**Windows**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**macOS / Linux**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

From the **project root**:

```bash
python evaluate.py
pytest tests -q
python run_daily_report.py --date 2024-05-20 --no-send-slack
python run_day.py --date 2024-05-20 --grain-min-avg 100 --top-n 5
adk web .
```

| Command | Notes |
|---------|--------|
| `evaluate.py` | 13/13 detector scenarios; no Gemini unless `--with-llm` |
| `pytest tests -q` | Unit tests; repo root on path via `pytest.ini` |
| `run_daily_report.py` | Pipeline + report; optional Slack; **no Gemini** |
| `run_day.py` | Pipeline + Gemini summary; writes `output/raw_anomalies_<date>.*` |
| `adk web .` | Chat UI on `:8000`; same live pipeline as CLI |

Defaults and overrides live in `config/settings.py` and `.env.example`. CLI flags override env where supported.

## How to use it

| Entry point | Command | Purpose |
|-------------|---------|---------|
| **CLI (LLM)** | `python run_day.py --date 2024-05-20` | Detect → export → Gemini summary to stdout |
| **Daily report** | `python run_daily_report.py --date 2024-05-20 --no-send-slack` | Detect → top issues → optional Slack |
| **ADK web** | `adk web .` | Browser chat; tool runs real pipeline |
| **HTTP API** | `uvicorn app.main:app --reload --host 127.0.0.1 --port 8080` | `GET /health`, `POST /internal/daily-report` |

**`run_day.py` flags (common)**

| Flag | Purpose |
|------|---------|
| `--csv PATH` | Force `local_csv` from this file |
| `--source` | `local_csv` or `databricks_mcp` (ignored if `--csv` set) |
| `--grain-min-avg`, `--top-n`, `--history-days`, `--z-threshold` | Detector / LLM subset tuning (defaults from env) |

**`run_daily_report.py` flags (common)**

| Flag | Purpose |
|------|---------|
| `--send-slack` / `--no-send-slack` | Control webhook delivery |
| `--source`, `--csv` | Same override rules as `run_day.py` |
| `--json` | Structured stdout |

Artifacts (all pipeline paths): `output/raw_anomalies_<YYYY-MM-DD>.json` and `.csv`.

## Architecture

All entry points call **`run_anomaly_pipeline()`** in `myagent/orchestration/pipeline_run.py`: resolve data source → `fetch_metrics()` → normalize → **`run_detection_pipeline_from_dataframe()`** in `myagent/pipeline.py`. LLM and Slack sit outside the detector core.

```text
         ┌─────────────────────┐
         │ data source         │
         │ local_csv /         │
         │ databricks_mcp      │
         └──────────┬──────────┘
                    │ fetch_metrics() → normalize
                    ▼
         ┌─────────────────────┐
         │ history window      │
         │ rule detectors      │
         └──────────┬──────────┘
                    ▼
         ┌─────────────────────┐
         │ enrich_anomalies()  │
         └──────────┬──────────┘
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
 raw exports    daily report    format for LLM
 (json/csv)     + Slack         → run_day / ADK
```

| Path | Role |
|------|------|
| `run_day.py` | Pipeline → ADK `InMemoryRunner` → stdout summary |
| `run_daily_report.py` / `POST /internal/daily-report` | Pipeline → top issues → optional Slack |
| `adk web` → `run_retail_data_quality_analysis` | Same pipeline via ADK tool |
| `uvicorn app.main:app` | Health + daily report HTTP trigger (`:8080`) |

## Data sources

| Provider | `RETAIL_DATA_SOURCE` | Notes |
|----------|----------------------|--------|
| Local CSV | `local_csv` (default) | `RETAIL_METRICS_CSV` or `data/retail_data_quality_sim.csv` |
| Databricks MCP | `databricks_mcp` | SQL via HTTP JSON-RPC `tools/call`; env-driven |

**Local CSV**

```bash
RETAIL_DATA_SOURCE=local_csv
RETAIL_METRICS_CSV=data/retail_data_quality_sim.csv
python run_day.py --date 2024-05-20 --csv data/retail_data_quality_sim.csv
```

**Databricks MCP** — client in `myagent/integrations/databricks_mcp_client.py`; provider in `myagent/data_sources/databricks_mcp.py`.

```bash
RETAIL_DATA_SOURCE=databricks_mcp
DATABRICKS_MCP_SERVER_URL=https://your-host/mcp
DATABRICKS_METRICS_CATALOG=retail
DATABRICKS_METRICS_SCHEMA=metrics
DATABRICKS_METRICS_TABLE=daily_store_metrics
```

Optional: `DATABRICKS_METRICS_SQL`, `DATABRICKS_MCP_TOOL_NAME` (default `execute_sql`), `DATABRICKS_MCP_AUTH_TOKEN`. Server must accept JSON-RPC `tools/call` with a `query` argument; rows are normalized to the same schema as the sample CSV. See `.env.example` for the full list.

## Slack

Daily report only — [Incoming Webhook](https://api.slack.com/messaging/webhooks), not an interactive Slack app or slash commands.

```bash
SLACK_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
python run_daily_report.py --date 2024-05-20 --send-slack
```

`run_day.py` does not send Slack. HTTP daily report can pass `send_slack=true` on `POST /internal/daily-report`.

## ADK web

From the project root (folder containing `myagent/`):

```bash
adk web .
```

1. Open the URL shown (default `http://127.0.0.1:8000`).
2. Select app **`myagent`**.
3. Example prompt: *“Analyze retail data quality for 2024-05-20 and summarize the most severe anomalies by store and department.”*

The agent calls **`run_retail_data_quality_analysis`**, which runs the same live pipeline as `run_day.py` (not canned data). Metrics come from `RETAIL_DATA_SOURCE`; use env for CSV or Databricks. Date in the message or `as_of_date` selects the day; otherwise latest `metricdate` in the data.

## HTTP API

Optional FastAPI sidecar — does **not** host the ADK chat UI.

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
curl -s http://127.0.0.1:8080/health
curl -s -X POST "http://127.0.0.1:8080/internal/daily-report?as_of_date=2024-05-20&send_slack=false"
```

Same orchestration as `run_daily_report.py`; no Gemini. Docker: `docker build -t retail-dq .` then `docker run -p 8080:8080 --env-file .env retail-dq`.

## Testing

```bash
python evaluate.py              # expect: Detector expectations: 13/13
python evaluate.py --with-llm   # optional; needs Gemini
pytest tests -q                 # 22 unit tests; mocked Slack/MCP
```

## Project layout

| Path | Role |
|------|------|
| `myagent/pipeline.py` | Core detectors, enrichment, exports |
| `myagent/orchestration/pipeline_run.py` | Shared `run_anomaly_pipeline()` |
| `myagent/orchestration/daily_report.py` | Daily report + Slack hook-up |
| `myagent/data_sources/` | `local_csv`, `databricks_mcp`, factory |
| `myagent/retail_tool.py` | ADK tool entry |
| `myagent/agent.py` | `root_agent` for `adk web` |
| `run_day.py` / `run_daily_report.py` | CLIs |
| `evaluate.py` | Labeled detector scenarios |
| `app/main.py` | FastAPI `/health`, `/internal/daily-report` |
| `config/settings.py` | Env-driven settings |
| `tests/` | Pytest suite |
| `data/` | Sample CSV |
| `.env.example` | Config template |
