# Retail Data Quality Agent

MCP-first ADK orchestration service for retail data quality analysis.

This repository is the agent/orchestration layer. The detection logic and Databricks access live in a paired MCP backend (`wfm_dq_mcp_server`). The supported production path is:

`ADK web (this repo) -> MCP backend -> Databricks SQL`

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Health, Readiness, and Diagnostics](#health-readiness-and-diagnostics)
- [Development Tools](#development-tools)
- [Testing](#testing)
- [Paired Local Run Profile](#paired-local-run-profile)
- [Security and Authentication](#security-and-authentication)
- [Observability and Logging](#observability-and-logging)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Active Surface Quality Boundary](#active-surface-quality-boundary)
- [Project Structure](#project-structure)
- [Legacy/Internal Paths](#legacyinternal-paths)

## Architecture

- `retail-data-quality-agent` (this repo): ADK agent setup, tool routing, compact summarization.
- `wfm_dq_mcp_server` (paired backend repo): MCP tools, Databricks query execution, DQ rules.
- ADK can invoke MCP over:
  - `stdio` (trusted local process boundary)
  - `sse` (remote endpoint with explicit bearer auth option)
- Business rules remain backend-owned to avoid duplicated logic in the agent layer.

## Prerequisites

- Python 3.10+ (3.11 recommended for container/CI parity)
- A working MCP backend checkout (`wfm_dq_mcp_server`)
- Databricks credentials configured in the MCP backend
- LLM credentials for ADK (Gemini/OpenAI/Anthropic/LiteLLM)

Optional but recommended:

- `uv` for faster dependency workflows
- Docker Desktop (for container verification)
- VS Code Dev Containers extension

## Development Setup

### Option 1: `uv` workflow (recommended)

`pyproject.toml` is now included as the canonical tool/task configuration. `requirements.txt` remains for compatibility.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install uv
uv sync
uv pip install -e ".[dev]"
```

### Option 2: pip workflow (fully supported)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
pip install poethepoet ruff pyright
```

### Dev Container

This repo includes `.devcontainer/devcontainer.json` for VS Code onboarding.

- Reopen project in container.
- Dependencies install automatically via `postCreateCommand`.
- Forwarded ports: `8000` (ADK UI), `8080` (companion API).

## Configuration

Copy `.env.example` to `.env` and set the required values.

Required for MCP-first runtime:

- `LLM_PROVIDER`
- Provider credential (`GOOGLE_API_KEY`, `OPENAI_API_KEY`, etc.)
- `WFM_DQ_MCP_TRANSPORT_FOR_ADK` (`stdio` or `sse`)

Transport-specific:

- `stdio` mode:
  - `WFM_DQ_MCP_SERVER_PATH_FOR_ADK` (absolute path to backend `server.py`)
  - optional `WFM_DQ_MCP_PYTHON_FOR_ADK`
- `sse` mode:
  - `WFM_DQ_MCP_SERVER_URL_FOR_ADK` (example: `http://127.0.0.1:8000/sse`)
  - optional `WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK` (Bearer token)
  - `WFM_DQ_MCP_REQUIRE_AUTH_FOR_SSE=true` to fail fast when token is missing

Common runtime settings:

- `LLM_MODEL`
- `WFM_DQ_MCP_SERVER_TIMEOUT_FOR_ADK` (default `90`)
- `LOG_LEVEL`, `LOG_FORMAT`
- `SERVICE_HOST`, `SERVICE_PORT` (companion FastAPI service)

Debug-only:

- `MCP_STDIO_DIAGNOSTICS=true` to emit one-line stdio diagnostics to `stderr` per MCP call.

## Running the Application

### ADK interface (primary product path)

```bash
adk web .
```

Then select app `myagent` in ADK web.

Remote SSE mode is also supported when `WFM_DQ_MCP_TRANSPORT_FOR_ADK=sse`.

### Companion HTTP API (health/readiness + internal trigger)

```bash
poe serve-api
```

Exposed endpoints:

- `GET /health` (liveness)
- `GET /ready` (config/readiness checks; returns `503` when not ready)
- `POST /internal/daily-report` (internal orchestration trigger)

## Health, Readiness, and Diagnostics

Local runtime doctor:

```bash
poe doctor
```

Deep stdio handshake diagnostic:

```bash
python -m tools.doctor --diagnose-mcp --timeout-seconds 60
```

Readiness checks include:

- LLM credential presence for selected provider
- MCP server path configured and script file exists

## Development Tools

Task runner: `poethepoet` (`poe`).

Available commands:

- `poe adk-web` - run ADK web UI
- `poe serve-api` - run FastAPI companion service
- `poe doctor` - runtime config diagnostics
- `poe paired-check` - validate paired local prerequisites
- `poe paired-up` - run local paired profile (SSE backend + ADK)
- `poe paired-up-stdio` - run ADK in stdio profile
- `poe lint` - ruff lint
- `poe format` - ruff format
- `poe format-check` - formatting check
- `poe type` - pyright
- `poe test` - pytest
- `poe check` - lint + format-check + type + tests

## Testing

Run active MCP-first test suite:

```bash
poe test
```

Current default test scope intentionally excludes quarantined legacy pipeline tests.

## Paired Local Run Profile

The recommended local end-to-end profile for reviewer demos is:

- MCP backend in `--sse` mode
- ADK agent in this repo using `WFM_DQ_MCP_TRANSPORT_FOR_ADK=sse`

Commands:

```bash
poe paired-check
poe paired-up
```

Behavior:

- Starts backend process from `WFM_DQ_MCP_SERVER_PATH_FOR_ADK` in SSE mode.
- Applies bind host/port from `WFM_DQ_MCP_SERVER_URL_FOR_ADK`.
- Starts `adk web .`.
- Terminates backend process when ADK process exits.

## Security and Authentication

Security boundary in this architecture:

- Agent repo holds LLM credentials and backend process path.
- MCP backend holds Databricks credentials and executes SQL.
- `stdio` mode is a trusted local process boundary.
- `sse` mode is a remote boundary and should be authenticated.

Operational guidance:

- Never commit `.env`.
- Use separate credentials for local/dev/prod.
- Restrict file permissions on `.env` and service account secrets.
- In production, run MCP backend in a controlled runtime and avoid broad host-level access.
- Treat `WFM_DQ_MCP_SERVER_PATH_FOR_ADK` as a trusted executable path; do not allow untrusted overrides.
- For remote SSE, require bearer token auth (`WFM_DQ_MCP_REQUIRE_AUTH_FOR_SSE=true` +
  `WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK`).

## Observability and Logging

- FastAPI service supports `console` and `json` logging via `LOG_FORMAT`.
- JSON logs include request correlation field `request_id`.
- HTTP middleware propagates/generates `x-request-id` for request tracing.
- MCP stdio diagnostics are available as an opt-in debug flag (`MCP_STDIO_DIAGNOSTICS`).

## Deployment

This repo includes a hardened container image:

- Multi-stage Docker build
- Non-root runtime user (`uid=10001`)
- Container healthcheck against `/health`

Build and run:

```bash
docker build -t retail-dq-agent .
docker run --rm -p 8080:8080 --env-file .env retail-dq-agent
```

`adk web .` is generally run separately in the target environment where interactive chat is required.

## Troubleshooting

### MCP tool calls timing out

1. Verify `WFM_DQ_MCP_SERVER_PATH_FOR_ADK` points to a valid backend `server.py`.
2. Set `WFM_DQ_MCP_PYTHON_FOR_ADK` to backend venv Python if dependencies differ.
3. Increase `WFM_DQ_MCP_SERVER_TIMEOUT_FOR_ADK` for cold starts.
4. Run `python -m tools.doctor --diagnose-mcp`.

### Remote SSE auth failures (`401 unauthorized`)

1. Ensure backend has `WFM_DQ_MCP_REQUIRE_AUTH=true`.
2. Ensure backend and agent share the same token value.
3. Set `WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK` in this repo.
4. Re-run `python -m tools.doctor --diagnose-mcp`.

### Readiness returns `not_ready`

1. Check `/ready` response details.
2. Ensure provider credentials match `LLM_PROVIDER`.
3. Ensure MCP transport-specific config is present:
   - stdio: server script path
   - sse: server URL (and token if auth is required)

### API boot fails

1. Confirm `.env` is present.
2. Run `poe doctor`.
3. Reinstall dependencies (`uv sync` or `pip install -r requirements.txt`).

## Active Surface Quality Boundary

Quality gates are intentionally scoped to the active MCP-first runtime and tests.
See `docs/QUALITY_BOUNDARY.md` for exact file coverage and rationale.

## Project Structure

```text
app/                         FastAPI companion service (health/readiness/internal trigger)
config/                      Shared settings
myagent/                     ADK root agent, tool adapter, MCP stdio integration
tests/                       Active MCP-first tests
tools/                       Diagnostics and utility scripts
_legacy/                     Internal-only legacy pipeline materials
Dockerfile                   Production-oriented API container
pyproject.toml               Tooling/tasks/lint/type config
requirements.txt             Compatibility dependency install path
```

## Legacy/Internal Paths

Local CSV/CLI pipeline flow is retained only for internal maintenance and is not a supported product runtime. The deployment target is MCP-first ADK plus Databricks-backed MCP backend.
