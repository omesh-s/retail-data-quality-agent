# Security Notes

## Trust Boundaries

- The ADK layer should not directly query Databricks.
- The MCP backend is the only component that needs Databricks secrets.
- `stdio` mode (`WFM_DQ_MCP_TRANSPORT_FOR_ADK=stdio`) is a trusted local process boundary.
- `sse` mode (`WFM_DQ_MCP_TRANSPORT_FOR_ADK=sse`) is a remote boundary and should be treated
  as untrusted network traffic.

## Secrets Management

- Keep secrets in `.env` (local) or secret manager (deployed runtime).
- Do not commit `.env` files.
- Scope service principals to least privilege (read-only table access where possible).

## Configuration Hardening

- Treat `WFM_DQ_MCP_SERVER_PATH_FOR_ADK` as trusted, immutable deployment config.
- Use explicit `WFM_DQ_MCP_PYTHON_FOR_ADK` in production to avoid interpreter drift.
- Restrict filesystem permissions so only service runtime can edit env/config files.
- For SSE mode:
  - configure `WFM_DQ_MCP_SERVER_URL_FOR_ADK`
  - set `WFM_DQ_MCP_REQUIRE_AUTH_FOR_SSE=true`
  - set `WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK` from a secret source

## Logging Safety

- Default to `LOG_FORMAT=json` for machine parsing.
- Do not log API keys, tokens, or full credential payloads.
- Enable `MCP_STDIO_DIAGNOSTICS` only for short-lived debugging sessions.

## Remote MCP Auth Pattern

Minimal supported pattern for non-stdio deployments:

1. Backend SSE runtime enforces bearer token when `WFM_DQ_MCP_REQUIRE_AUTH=true`.
2. Agent sends `Authorization: Bearer <token>` when `WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK` is set.
3. Missing/invalid token returns `401 unauthorized` from backend SSE endpoint.

This provides explicit baseline authentication without introducing heavyweight IAM dependencies.
