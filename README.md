# Retail Data Quality Agent (MCP-First)

This repository is the **ADK agent layer** for retail data quality analysis.

The analysis backend is an **external MCP server** that queries Databricks SQL and applies the business rules.

Primary product path:

```bash
adk web .
```

## Paired Architecture

- **This repo** (`retail-data-quality-agent`) = ADK orchestration + concise business summarization
- **MCP server repo/folder** (`wfm_dq_mcp_server`) = Databricks-backed API/backend logic

```mermaid
flowchart LR
  User[User] --> ADK[ADK Agent (this repo)]
  ADK --> MCP[MCP Server (paired backend repo)]
  MCP --> DB[Databricks SQL]
  DB --> MCP
  MCP --> ADK
  ADK --> Answer[Business summary]
```

## What This Project Does

- Exposes a root ADK agent (`myagent`) for chat-based data quality workflows
- Routes questions to MCP tools (full analysis, metadata lookup, derived validation)
- Normalizes and compacts tool output for lower token usage (`myagent/anomaly_to_prompt.py`)
- Keeps explanation thin: tool selection, prioritization, concise interpretation

Business rule source of truth remains in the MCP backend.

## Prerequisites

### For this repo (ADK agent)

- Python 3.10+
- `google-adk` compatible environment
- Gemini or other configured LLM credentials
- Path to the paired MCP server script (`server.py`)

### For the paired MCP backend repo

- Python 3.10+
- Databricks SQL access
- OAuth M2M credentials and SQL warehouse HTTP path configured in that repo’s `.env`

## Quick Start (Supported Path)

```bash
# 1) From this repo
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # macOS/Linux
pip install -r requirements.txt

# 2) Configure this repo
copy .env.example .env
# then set at minimum:
#   LLM_PROVIDER
#   LLM_MODEL
#   GOOGLE_API_KEY (or provider equivalent)
#   WFM_DQ_MCP_SERVER_PATH_FOR_ADK
#   optional: WFM_DQ_MCP_PYTHON_FOR_ADK

# 3) Launch ADK
adk web .
```

In ADK UI, select the `myagent` app.

## MCP Backend Setup Expectations

In the paired MCP repo/folder (`wfm_dq_mcp_server`):

1. Create/activate its venv
2. Install its requirements
3. Set its Databricks `.env` values
4. Verify server starts:

```bash
python server.py
```

This repo calls that MCP server over stdio via `WFM_DQ_MCP_SERVER_PATH_FOR_ADK`.

## Environment Variables (This Repo)

Core MCP-first settings:

- `LLM_PROVIDER` (default `googlegenai`)
- `LLM_MODEL` (default `gemini-2.5-flash`)
- `GOOGLE_API_KEY` (or equivalent provider key)
- `WFM_DQ_MCP_SERVER_PATH_FOR_ADK` (absolute path to paired MCP `server.py`)
- `WFM_DQ_MCP_PYTHON_FOR_ADK` (optional interpreter override)
- `WFM_DQ_MCP_SERVER_TIMEOUT_FOR_ADK` (default 90)
- `LOG_LEVEL`, `LOG_FORMAT`

See `.env.example` for the template.

## MCP Tool Surface (From Backend)

The agent expects these backend tools:

- `get_available_dates` — available date range
- `run_full_dq_analysis` — full rule execution on Databricks-backed data
- `get_metric_info` — metric metadata/formula lookup
- `validate_derived_metric` — targeted derived formula validation (if available)

If a targeted tool is unavailable, the agent falls back gracefully to broad analysis.

## Example Prompts

- `Analyze data quality for 2026-05-15 with 14 day lookback.`
- `Are any 7-day drops isolated or systemic across stores on 2026-05-10?`
- `Show large negative outliers and separate small reversals from suspicious negatives.`
- `Validate TEST10_TOT for Bakery on 2026-05-01 and show mismatched stores with csv value, expected value, and error percentage.`
- `What does TEST10_TOT roll up from?`

## Stdio vs SSE

- **Stdio** is the default and supported path for ADK in this setup.
- **SSE** is optional in the MCP backend for remote/multi-client deployments.

## Legacy Path Status

Local CSV/CLI pipeline code is now **internal/dev-only legacy** and not the supported product path.

Supported product path is:

`ADK web + MCP backend + Databricks SQL`.
