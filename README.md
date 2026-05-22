# Retail Data Quality Agent

Monitors daily retail store metrics with **deterministic pandas rules**, enriches findings with severity scores, and optionally summarizes via **LLM** (CLI/ADK) or **Slack** (daily report). One shared provider-backed pipeline powers every entry point.

**What it does**

- Shared anomaly pipeline (`myagent/pipeline.py`) — detectors, enrichment, exports
- CLI + ADK web — same `run_anomaly_pipeline()` backend
- Daily report + optional **Slack** incoming webhook (no LLM)
- Optional FastAPI companion (`/health`, daily-report trigger)
- Data sources: **`local_csv`** (default) or **`databricks_mcp`** (HTTP JSON-RPC client)

**Requirements:** Python 3.11+ (tested on 3.13). Run `python setup_wizard.py` for guided setup (or copy `.env.example` → `.env`). Gemini/Google credentials for `run_day.py` and `adk web` when `LLM_PROVIDER=googlegenai`.

## Quick start

**Windows**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python setup_wizard.py
```

**macOS / Linux**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python setup_wizard.py
```

```bash
python evaluate.py
pytest tests -q
python run_daily_report.py --date 2024-05-20 --no-send-slack
python run_day.py --date 2024-05-20 --grain-min-avg 100 --top-n 5
adk web .
```

| Command | Notes |
|---------|--------|
| `setup_wizard.py` | Guided `.env` setup (curated models, optional advanced settings) |
| `evaluate.py` | 13/13 detector scenarios; no LLM unless `--with-llm` |
| `pytest tests -q` | Unit tests (`pytest.ini` adds repo root to path) |
| `run_daily_report.py` | Pipeline + report; optional Slack; **no Gemini** |
| `run_day.py` | Pipeline + LLM summary; writes `output/raw_anomalies_<date>.*` |
| `adk web .` | Chat UI (`:8000`); same live pipeline as CLI |

## Setup wizard

`python setup_wizard.py` — guided **basic** setup; advanced pipeline tuning is optional.

| Step | What you configure |
|------|-------------------|
| LLM | Provider → **curated model list** (or custom). LiteLLM asks provider family, then routed model presets. |
| Data | Sample CSV if present, or Databricks MCP |
| Slack | Off by default; webhook validated when enabled |
| Scheduler | Off by default; timezone accepts IANA or aliases (CST → `America/Chicago`) |
| Advanced | Skipped by default (30d history, z=4.0, grain distinct=3, report top-N=10) |

- **ADK web** remains Google GenAI / Gemini; other providers mainly affect `run_day.py`.
- **Gemini:** Google GenAI → `gemini-2.5-flash` → `GOOGLE_API_KEY`.
- **LiteLLM → Claude:** LiteLLM → Anthropic / Claude → `anthropic/claude-3-5-sonnet-20241022`.
- Edit `.env` later for advanced keys without re-running the wizard.
- **Scheduler timezone:** type `America/Chicago`, `CST`, `Central`, or `Chicago` — saved as canonical IANA (e.g. `America/Chicago`).

## How to use it

| Entry point | Command | Purpose |
|-------------|---------|---------|
| **CLI (LLM)** | `python run_day.py --date 2024-05-20` | Detect → export → summary (`googlegenai` uses ADK; others use `myagent/llm`) |
| **Daily report** | `python run_daily_report.py --date 2024-05-20` | Detect → top issues → Slack per config/flags |
| **Scheduler** | `python schedule_daily_report.py --once` | Cron-friendly single run; `--loop` for local daily time |
| **ADK web** | `adk web .` | Browser chat; tool runs real pipeline |
| **HTTP API** | `uvicorn app.main:app --host 127.0.0.1 --port 8080` | `GET /health`, `POST /internal/daily-report` |

**Common flags:** `--csv` forces `local_csv`; `--source` overrides `RETAIL_DATA_SOURCE`; `--send-slack` / `--no-send-slack` override Slack for that run.

Artifacts: `output/raw_anomalies_<YYYY-MM-DD>.json` and `.csv`.

## Architecture

`run_anomaly_pipeline()` (`myagent/orchestration/pipeline_run.py`) resolves a data source → `fetch_metrics()` → schema normalization → `run_detection_pipeline_from_dataframe()`. LLM and Slack are outside the detector core.

```text
  data source (local_csv / databricks_mcp)
           │ fetch_metrics → normalize (aliases)
           ▼
  history window → rule detectors → enrich_anomalies
           │
     ┌─────┴─────┬─────────────┐
     ▼           ▼             ▼
  exports   daily report    LLM prompt
            + Slack         (run_day / ADK)
```

## Data sources

| Provider | `RETAIL_DATA_SOURCE` | Notes |
|----------|----------------------|--------|
| Local CSV / Parquet | `local_csv` | `RETAIL_METRICS_CSV` or sample `data/retail_data_quality_sim.csv` |
| Databricks MCP | `databricks_mcp` | **MCP client** over HTTP JSON-RPC `tools/call` (not a bundled MCP server) |

**Local**

```bash
RETAIL_DATA_SOURCE=local_csv
RETAIL_METRICS_CSV=data/retail_data_quality_sim.csv
```

**Databricks MCP** — env-driven client in `myagent/integrations/databricks_mcp_client.py`:

```bash
RETAIL_DATA_SOURCE=databricks_mcp
DATABRICKS_MCP_SERVER_URL=https://your-host/mcp
DATABRICKS_METRICS_CATALOG=retail
DATABRICKS_METRICS_SCHEMA=metrics
DATABRICKS_METRICS_TABLE=daily_store_metrics
```

**Column aliases:** variant names (`store_id`, `business_date`, …) map via `config/schema_aliases.py`. Optional `DATA_SCHEMA_MAP_FILE` JSON override. Large files: optional `DATA_READ_CHUNK_SIZE`, `DATA_USE_PYARROW=true`, Parquet supported.

## Slack

Incoming webhook for **daily report only** — not an interactive Slack bot.

```bash
SLACK_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
DAILY_REPORT_DEFAULT_SEND_SLACK=true   # auto-send when webhook set
python run_daily_report.py --date 2024-05-20 --send-slack
python tools/test_slack.py
```

**Local schedule:** `DAILY_REPORT_ENABLED=true`, then `python schedule_daily_report.py --loop`. Production: cron or Cloud Scheduler calling `--once` or the HTTP endpoint.

## ADK web

```bash
adk web .
```

Select **`myagent`**. Example: *“Analyze retail data quality for 2024-05-20 and summarize severe anomalies by store and department.”*

Uses tool **`run_retail_data_quality_analysis`** (live pipeline, not canned data). Requires `LLM_PROVIDER=googlegenai` and Google credentials. Model from `LLM_MODEL` (default `gemini-2.5-flash`).

## HTTP API

Optional sidecar — does not host ADK chat.

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
curl -s http://127.0.0.1:8080/health
curl -s -X POST "http://127.0.0.1:8080/internal/daily-report?as_of_date=2024-05-20&send_slack=false"
```

## LLM providers

| `LLM_PROVIDER` | Used by | Credentials |
|----------------|---------|-------------|
| `googlegenai` (default) | `run_day.py`, `adk web` | `GOOGLE_API_KEY` |
| `openai` | `run_day.py` (direct API) | `OPENAI_API_KEY` |
| `anthropic` | `run_day.py` (direct API) | `ANTHROPIC_API_KEY` |
| `litellm` | `run_day.py` (via litellm) | `LITELLM_API_KEY` / `LITELLM_API_BASE` |

ADK web remains on the Google ADK path today.

## Testing

```bash
python evaluate.py
python evaluate.py --with-llm
pytest tests -q
```

## Project layout

| Path | Role |
|------|------|
| `myagent/pipeline.py` | Core detectors + enrichment |
| `myagent/orchestration/pipeline_run.py` | `run_anomaly_pipeline()` |
| `myagent/data_sources/` | `local_csv`, `databricks_mcp` |
| `config/settings.py` | Typed env settings |
| `config/schema_aliases.py` | Column alias normalization |
| `config/setup_wizard.py` | Wizard logic; `setup_wizard.py` entry point |
| `config/wizard_llm.py` | LLM model presets and validation |
| `schedule_daily_report.py` | Daily run / local loop |
| `run_day.py` / `run_daily_report.py` | CLIs |
| `tools/test_slack.py` | Webhook smoke test |
| `app/main.py` | FastAPI companion |
| `.env.example` | Config template |

**Migration:** Slack auto-send when `send_slack` is omitted now follows `SLACK_ENABLED` **or** `DAILY_REPORT_DEFAULT_SEND_SLACK` (plus webhook). Use `--no-send-slack` to force off.
