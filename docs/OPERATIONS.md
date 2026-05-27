# Operations Runbook

## Runtime Topology

- ADK agent runtime: this repository
- MCP backend runtime: paired `wfm_dq_mcp_server` repository
- Data plane: Databricks SQL (accessed only by MCP backend)

## Startup Order

1. Validate backend credentials in `wfm_dq_mcp_server/.env`.
2. Ensure backend `server.py` starts with its venv interpreter.
3. Set this repo `.env` values, including MCP transport config.
4. Run `poe doctor` in this repo.
5. Start ADK UI with `adk web .`.

For local paired profile:

```bash
poe paired-check
poe paired-up
```

## Health Checks

- Liveness: `GET /health`
- Readiness: `GET /ready`
- Local diagnostics: `python -m tools.doctor --diagnose-mcp`

## Incident Triage

### Symptom: MCP timeout

- Verify backend process starts manually with the same Python interpreter.
- Increase `WFM_DQ_MCP_SERVER_TIMEOUT_FOR_ADK`.
- Enable `MCP_STDIO_DIAGNOSTICS=true` temporarily.
- Collect `python -m tools.doctor --diagnose-mcp` output.

### Symptom: SSE authentication failures

- Ensure backend env has `WFM_DQ_MCP_REQUIRE_AUTH=true`.
- Ensure backend and agent tokens match.
- Check that ADK transport is set to `sse` and URL points to `/sse`.

### Symptom: empty or unexpected anomaly output

- Verify date range with backend `get_available_dates`.
- Confirm `check_date` and `dept_desc` filters.
- Validate backend table/credentials in paired MCP server.

### Symptom: readiness not ready

- Read `/ready` checks for exact failing component.
- Fix credentials/path and retry.
