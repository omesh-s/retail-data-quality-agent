"""Minimal HTTP JSON-RPC client for Databricks-style MCP SQL tools.

Assumes the MCP server exposes a ``tools/call`` JSON-RPC method that accepts a
configurable tool name (default ``execute_sql``) with a ``query`` argument and
returns tabular rows as JSON in the tool result text.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

from config.settings import Settings

logger = logging.getLogger(__name__)


class DatabricksMcpClientError(RuntimeError):
    """MCP request or response parsing failed."""


def _redact_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/…" if parsed.netloc else "<invalid-url>"


class DatabricksMcpClient:
    """Execute SQL via an MCP server's tool invocation over HTTP JSON-RPC."""

    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self._settings = settings
        self._session = session or requests.Session()

    def execute_sql(self, sql: str) -> pd.DataFrame:
        """Run *sql* through the configured MCP tool and return a raw DataFrame."""
        url = (self._settings.databricks_mcp_server_url or "").strip()
        if not url:
            raise DatabricksMcpClientError("DATABRICKS_MCP_SERVER_URL is not set")

        tool_name = self._settings.databricks_mcp_tool_name
        timeout = self._settings.databricks_mcp_timeout_seconds
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = self._settings.databricks_mcp_auth_token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": {"query": sql},
            },
        }

        logger.info(
            "Databricks MCP tools/call tool=%s host=%s",
            tool_name,
            _redact_url(url),
        )
        try:
            response = self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise DatabricksMcpClientError(f"MCP HTTP request failed: {exc}") from exc

        if response.status_code >= 400:
            raise DatabricksMcpClientError(
                f"MCP HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise DatabricksMcpClientError("MCP response is not valid JSON") from exc

        if "error" in body:
            err = body["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise DatabricksMcpClientError(f"MCP error: {msg}")

        rows = _extract_rows_from_mcp_result(body.get("result", body))
        if not rows:
            logger.warning("Databricks MCP returned zero rows")
            return pd.DataFrame()
        return pd.DataFrame(rows)


def _extract_rows_from_mcp_result(result: Any) -> list[dict[str, Any]]:
    """Parse common MCP tool result shapes into row dicts."""
    if result is None:
        return []

    if isinstance(result, list):
        if result and isinstance(result[0], dict):
            return result
        return []

    if isinstance(result, dict):
        if "rows" in result and isinstance(result["rows"], list):
            return [r for r in result["rows"] if isinstance(r, dict)]
        if "data" in result and isinstance(result["data"], list):
            return [r for r in result["data"] if isinstance(r, dict)]

        content = result.get("content")
        if isinstance(content, list):
            texts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(str(part.get("text", "")))
            return _parse_text_payload("\n".join(texts))

        if "text" in result:
            return _parse_text_payload(str(result["text"]))

    if isinstance(result, str):
        return _parse_text_payload(result)

    return []


def _parse_text_payload(text: str) -> list[dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _parse_csv_text(text)

    if isinstance(parsed, list):
        return [r for r in parsed if isinstance(r, dict)]
    if isinstance(parsed, dict):
        for key in ("rows", "data", "records"):
            if key in parsed and isinstance(parsed[key], list):
                return [r for r in parsed[key] if isinstance(r, dict)]
    return []


def _parse_csv_text(text: str) -> list[dict[str, Any]]:
    import io

    try:
        frame = pd.read_csv(io.StringIO(text))
    except Exception:
        return []
    return frame.to_dict(orient="records")
