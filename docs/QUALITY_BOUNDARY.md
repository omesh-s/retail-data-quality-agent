# Active Surface Quality Boundary

This project intentionally enforces lint/type quality on the active MCP-first runtime surface, not the quarantined legacy modules.

## Included in quality gates

- `app/` runtime API surface:
  - `app/main.py`
  - `app/logging_setup.py`
  - `app/request_context.py`
  - `app/api/routes/health.py`
  - `app/schemas/responses.py`
- `config/settings.py`
- Agent MCP-first path:
  - `myagent/__init__.py`
  - `myagent/agent.py`
  - `myagent/retail_tool.py`
  - `myagent/anomaly_to_prompt.py`
  - `myagent/integrations/mcp_stdio_client.py`
  - `myagent/integrations/mcp_sse_client.py`
- Runtime tooling:
  - `tools/doctor.py`
  - `tools/paired_run.py`
- Active tests:
  - `tests/test_adk_mcp_integration.py`
  - `tests/test_retail_tool.py`
  - `tests/test_anomaly_to_prompt.py`
  - `tests/test_settings.py`
  - `tests/test_mcp_stdio_client.py`
  - `tests/test_mcp_sse_client.py`
  - `tests/test_service_health.py`

## Why this boundary

- It covers the MCP-first production path that is currently owned and supported.
- It avoids blocking releases on historical modules that are no longer product-critical.
- It provides a realistic senior-review bar without pretending the entire repository has been fully modernized.

## Command

Use `poe check` to run the active-surface gate (`ruff`, `pyright`, `pytest`).
