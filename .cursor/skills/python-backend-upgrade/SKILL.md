---
name: python-backend-upgrade
description: >-
  Guides backend and companion HTTP service work in the retail data quality
  agent repo: FastAPI routes, pydantic-settings, structured logging, health
  probes, and safe incremental refactors. Use when adding or changing app/,
  config/, API endpoints, service config, logging, Docker/uvicorn setup, or
  when the user mentions backend upgrade, FastAPI, health checks, or service
  layer tasks.
---

# Python backend upgrade

Use this skill when working on backend/service tasks in this repo.

## Focus

- Python project structure
- FastAPI routes
- pydantic-settings config
- structured logging
- health/readiness endpoints
- safe incremental refactors

## Constraints

- preserve existing pipeline behavior
- avoid breaking ADK discovery
- avoid unnecessary abstraction
- prefer simple, testable code
- keep public-safe naming and config

## Repo map

| Area | Role |
|------|------|
| `myagent/pipeline.py` | **Source of truth** for anomaly detection — do not fork logic into `app/` |
| `myagent/agent.py` | ADK root agent (`root_agent`) — keep discoverable by `adk web .` |
| `myagent/retail_tool.py` | ADK tool; reads `config.settings` for pipeline params |
| `app/main.py` | FastAPI entry; mounts routers, validation handler, startup log |
| `app/api/routes/` | HTTP routes (e.g. `health.py`) |
| `app/schemas/` | Pydantic response models shared by routes |
| `app/logging_setup.py` | `configure_logging()` — console, JSON, or YAML dictConfig |
| `config/settings.py` | `Settings` + `get_settings()` — env + `.env`, `@lru_cache` |
| `config/logging/*.yaml` | Optional dictConfig presets |

**Separation:** The HTTP companion uses settings for **service/logging** only today. Any future pipeline-over-HTTP must call `run_detection_pipeline` from `myagent/pipeline.py`, same as CLI/ADK.

## Workflow

1. **Read before edit** — inspect `app/main.py`, relevant route, `config/settings.py`, and `.env.example`.
2. **Small diff** — one concern per change (route, setting, log format, schema).
3. **Config** — add fields to `Settings` with `Field`, `AliasChoices`, validators; document in `.env.example` (no secrets).
4. **Routes** — new modules under `app/api/routes/`, `APIRouter`, Pydantic `response_model`, register in `app/main.py`.
5. **Logging** — use `logging.getLogger(__name__)`; call `configure_logging()` only from app startup path (already in `main.py`).
6. **Do not break** — `run_day.py`, `evaluate.py`, `adk web .`, README workflows.

## Patterns to follow

### Settings

```python
# config/settings.py — extend Settings, not os.environ scattered in app code
some_flag: bool = Field(
    default=False,
    validation_alias=AliasChoices("SOME_FLAG", "some_flag"),
)
```

Tests that change env: `get_settings.cache_clear()` before re-reading.

### Health / readiness

- **Liveness:** `GET /health` → `HealthResponse` (`app/api/routes/health.py`).
- **Readiness (if added):** separate route (e.g. `/ready`) only when there is a real dependency to check; keep handlers cheap and synchronous unless I/O is unavoidable.

### FastAPI errors

Reuse `ErrorResponse` and the existing `RequestValidationError` handler in `app/main.py` for consistent JSON errors.

### ADK discovery

- Keep `myagent/agent.py` exporting `root_agent`.
- Do not rename `myagent/` package or move agent entry without updating ADK docs/README.
- Default HTTP bind: `127.0.0.1:8080` — leave ADK web on its usual port (~8000).

### Naming and safety

- No company-specific names, internal URLs, certs, or secrets in code or docs.
- Public-safe service names in schemas (e.g. `retail-data-quality-api`).

## Anti-patterns

- Duplicating detection/enrichment logic in `app/`
- New framework layers (DI containers, generic “service base” classes) without a concrete need
- Breaking changes to `RETAIL_*` env semantics used by CLI and `retail_tool`
- Heavy middleware or auth scaffolding unless explicitly requested

## Verify after changes

```bash
# Deterministic pipeline (no LLM)
python evaluate.py

# FastAPI health (from repo root, venv active)
uvicorn app.main:app --host 127.0.0.1 --port 8080
# Then: curl http://127.0.0.1:8080/health

# ADK still discovers agent (requires Gemini config for full chat)
adk web .
```

Summarize for the user: files touched, why, and exact commands run.

## When unsure

Inspect repo layout and README architecture section before choosing where code belongs. Prefer extending existing modules over new top-level packages.
