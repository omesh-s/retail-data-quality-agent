"""Synchronous MCP stdio client for single tool calls.

Uses the official MCP Python client/session implementation for protocol
correctness (initialize + tools/call framing) and wraps it in a small
sync API used by the ADK adapter.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)


class McpStdioError(RuntimeError):
    """Raised when the MCP stdio interaction fails."""


@dataclass
class McpToolResult:
    """Parsed result from an MCP ``tools/call`` response."""

    content_text: str
    is_error: bool = False


def _flatten_tool_text(content: list[Any]) -> str:
    texts: list[str] = []
    for part in content or []:
        if isinstance(part, dict):
            if part.get("type") == "text":
                texts.append(str(part.get("text", "")))
            continue
        text_attr = getattr(part, "text", None)
        if text_attr is not None:
            texts.append(str(text_attr))
    return "\n".join(t for t in texts if t)


async def _call_mcp_tool_async(
    *,
    command: str,
    script: Path,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float,
    errlog_path: Path,
) -> McpToolResult:
    params = StdioServerParameters(
        command=command,
        args=[str(script)],
        cwd=str(script.parent),
        env={**os.environ},
    )
    with errlog_path.open("w", encoding="utf-8") as errlog:
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(
                    session.initialize(),
                    timeout=timeout_seconds,
                )
                call_result = await asyncio.wait_for(
                    session.call_tool(
                        tool_name,
                        arguments,
                        read_timeout_seconds=timedelta(seconds=timeout_seconds),
                    ),
                    timeout=timeout_seconds,
                )
    return McpToolResult(
        content_text=_flatten_tool_text(getattr(call_result, "content", [])),
        is_error=bool(getattr(call_result, "isError", False)),
    )


def _stderr_tail(errlog_path: Path, *, max_chars: int = 1200) -> str:
    try:
        text = errlog_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return text[-max_chars:] if len(text) > max_chars else text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def call_mcp_tool(
    server_script: str | Path,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout_seconds: float = 120.0,
    python_executable: str | None = None,
) -> McpToolResult:
    """Spawn an MCP server and call one tool via stdio.

    Process startup details:
    - command: `python_executable` if provided, else `sys.executable`
    - args: absolute `server_script` path
    - cwd: parent directory of `server_script`
    """
    script = Path(server_script).resolve()
    if not script.is_file():
        raise McpStdioError(f"MCP server script not found: {script}")

    command = python_executable or sys.executable
    diagnostics_enabled = os.getenv("MCP_STDIO_DIAGNOSTICS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if diagnostics_enabled:
        sys.stderr.write(
            f"[MCP STDIO] tool={tool_name} cmd={[command, str(script)]} "
            f"cwd={script.parent} timeout={timeout_seconds}s\n"
        )
    logger.info(
        "MCP stdio call: command=%s script=%s cwd=%s tool=%s timeout=%ss",
        command,
        script,
        script.parent,
        tool_name,
        timeout_seconds,
    )
    errlog = Path(tempfile.gettempdir()) / f"mcp_stdio_{os.getpid()}_{tool_name}.log"
    try:
        return asyncio.run(
            _call_mcp_tool_async(
                command=command,
                script=script,
                tool_name=tool_name,
                arguments=arguments,
                timeout_seconds=timeout_seconds,
                errlog_path=errlog,
            )
        )
    except asyncio.TimeoutError as exc:
        stderr = _stderr_tail(errlog)
        raise McpStdioError(
            "MCP stdio timeout during initialize/tool call. "
            f"tool={tool_name} timeout={timeout_seconds}s "
            f"command={command} script={script} cwd={script.parent}"
            + (f"\nServer stderr tail:\n{stderr}" if stderr else "")
        ) from exc
    except Exception as exc:
        stderr = _stderr_tail(errlog)
        raise McpStdioError(
            "MCP stdio call failed. "
            f"tool={tool_name} command={command} script={script} cwd={script.parent} "
            f"error={type(exc).__name__}: {exc}"
            + (f"\nServer stderr tail:\n{stderr}" if stderr else "")
        ) from exc


def diagnose_mcp_stdio_call(
    server_script: str | Path,
    *,
    python_executable: str | None = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Diagnostic helper for stdio handshake and simple tool call."""
    script = Path(server_script).resolve()
    command = python_executable or sys.executable
    errlog = Path(tempfile.gettempdir()) / f"mcp_stdio_diag_{os.getpid()}.log"
    result: dict[str, Any] = {
        "command": command,
        "script": str(script),
        "cwd": str(script.parent),
        "timeout_seconds": timeout_seconds,
    }
    try:
        tool_result = asyncio.run(
            _call_mcp_tool_async(
                command=command,
                script=script,
                tool_name="get_metric_info",
                arguments={"metric_cd": "TEST10_TOT"},
                timeout_seconds=timeout_seconds,
                errlog_path=errlog,
            )
        )
        result["ok"] = True
        result["is_error"] = tool_result.is_error
        result["content_preview"] = tool_result.content_text[:500]
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["stderr_tail"] = _stderr_tail(errlog)
    return result
