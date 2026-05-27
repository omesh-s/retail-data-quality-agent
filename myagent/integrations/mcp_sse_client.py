"""Synchronous MCP SSE client for single tool calls."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

from myagent.integrations.mcp_stdio_client import McpStdioError, McpToolResult


def _auth_headers(auth_token: str | None) -> dict[str, str] | None:
    if not auth_token:
        return None
    return {"Authorization": f"Bearer {auth_token}"}


async def _call_mcp_tool_sse_async(
    *,
    server_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float,
    auth_token: str | None,
) -> McpToolResult:
    headers = _auth_headers(auth_token)
    async with sse_client(
        url=server_url,
        headers=headers,
        timeout=timeout_seconds,
        sse_read_timeout=timeout_seconds,
    ) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await asyncio.wait_for(session.initialize(), timeout=timeout_seconds)
            call_result = await asyncio.wait_for(
                session.call_tool(
                    tool_name,
                    arguments,
                    read_timeout_seconds=timedelta(seconds=timeout_seconds),
                ),
                timeout=timeout_seconds,
            )

    text_parts: list[str] = []
    for part in getattr(call_result, "content", []) or []:
        text_attr = getattr(part, "text", None)
        if text_attr is not None:
            text_parts.append(str(text_attr))
    return McpToolResult(
        content_text="\n".join(p for p in text_parts if p),
        is_error=bool(getattr(call_result, "isError", False)),
    )


def call_mcp_tool_sse(
    *,
    server_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float = 120.0,
    auth_token: str | None = None,
) -> McpToolResult:
    try:
        return asyncio.run(
            _call_mcp_tool_sse_async(
                server_url=server_url,
                tool_name=tool_name,
                arguments=arguments,
                timeout_seconds=timeout_seconds,
                auth_token=auth_token,
            )
        )
    except Exception as exc:
        raise McpStdioError(
            "MCP SSE call failed. "
            f"url={server_url} tool={tool_name} error={type(exc).__name__}: {exc}"
        ) from exc


def diagnose_mcp_sse_call(
    *,
    server_url: str,
    timeout_seconds: float = 120.0,
    auth_token: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "server_url": server_url,
        "timeout_seconds": timeout_seconds,
        "auth_enabled": bool(auth_token),
    }
    try:
        tool_result = call_mcp_tool_sse(
            server_url=server_url,
            tool_name="get_metric_info",
            arguments={"metric_cd": "TEST10_TOT"},
            timeout_seconds=timeout_seconds,
            auth_token=auth_token,
        )
        result["ok"] = True
        result["is_error"] = tool_result.is_error
        preview = tool_result.content_text[:500] if tool_result.content_text else ""
        if preview:
            try:
                parsed = json.loads(preview)
                result["content_preview"] = json.dumps(parsed, separators=(",", ":"))[:500]
            except json.JSONDecodeError:
                result["content_preview"] = preview
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result
