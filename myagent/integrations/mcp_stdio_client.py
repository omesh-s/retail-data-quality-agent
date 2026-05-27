"""Lightweight synchronous MCP stdio client for single tool calls.

Spawns an MCP server as a subprocess, performs the JSON-RPC initialize
handshake, calls one tool, and shuts down.  Used by the ``mcp_server``
data source mode in ``pipeline_run.py``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class McpStdioError(RuntimeError):
    """Raised when the MCP stdio interaction fails."""


@dataclass
class McpToolResult:
    """Parsed result from an MCP ``tools/call`` response."""

    content_text: str
    is_error: bool = False


# ---------------------------------------------------------------------------
# Wire helpers (Content-Length framed JSON-RPC over stdin/stdout)
# ---------------------------------------------------------------------------

def _write_msg(proc: subprocess.Popen, msg: dict) -> None:
    body = json.dumps(msg).encode("utf-8")
    frame = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    proc.stdin.write(frame)
    proc.stdin.flush()


def _read_msg(proc: subprocess.Popen) -> dict:
    buf = b""
    while b"\r\n\r\n" not in buf and b"\n\n" not in buf:
        ch = proc.stdout.read(1)
        if not ch:
            raise McpStdioError("MCP server closed stdout unexpectedly")
        buf += ch

    if b"\r\n\r\n" in buf:
        header_raw, _sep, _rest = buf.partition(b"\r\n\r\n")
    else:
        header_raw, _sep, _rest = buf.partition(b"\n\n")

    length: int | None = None
    header_text = header_raw.decode("ascii").replace("\r\n", "\n")
    for line in header_text.split("\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            break
    if length is None or length <= 0:
        raise McpStdioError(f"No Content-Length in header: {buf!r}")

    body = proc.stdout.read(length)
    if len(body) != length:
        raise McpStdioError(f"Short read: expected {length} bytes, got {len(body)}")
    return json.loads(body)


def _read_response(proc: subprocess.Popen, request_id: int) -> dict:
    """Read messages until we get a JSON-RPC response matching *request_id*."""
    while True:
        msg = _read_msg(proc)
        if "id" in msg and msg["id"] == request_id:
            return msg


def _drain_stderr(proc: subprocess.Popen) -> str:
    """Best-effort stderr capture after an error (non-blocking)."""
    try:
        proc.kill()
        _, err = proc.communicate(timeout=3)
        return err.decode("utf-8", errors="replace")[:500].strip()
    except Exception:
        return ""


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
    """Spawn an MCP server, call one tool, return the result, then shut down.

    The server runs with its parent directory as CWD so it can load its own
    ``.env`` and sibling modules.

    Raises :class:`McpStdioError` on communication failure, timeout, or a
    JSON-RPC error response from the server.
    """
    script = Path(server_script).resolve()
    if not script.is_file():
        raise McpStdioError(f"MCP server script not found: {script}")

    cmd = [python_executable or sys.executable, str(script)]
    logger.info("MCP stdio: starting %s (cwd=%s)", cmd, script.parent)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(script.parent),
        env={**os.environ},
    )

    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        proc.kill()

    timer = threading.Timer(timeout_seconds, _kill)
    timer.start()

    try:
        # 1) Initialize handshake
        _write_msg(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "retail-dq-agent", "version": "1.0.0"},
            },
        })
        _read_response(proc, 1)

        # 2) Initialized notification (no response expected)
        _write_msg(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3) Tool call
        _write_msg(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        resp = _read_response(proc, 2)

        if "error" in resp:
            err = resp["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise McpStdioError(f"MCP server error: {msg}")

        result = resp.get("result", {})
        texts = [
            p.get("text", "")
            for p in result.get("content", [])
            if isinstance(p, dict) and p.get("type") == "text"
        ]

        return McpToolResult(
            content_text="\n".join(texts),
            is_error=result.get("isError", False),
        )

    except Exception as exc:
        if timed_out.is_set():
            raise McpStdioError(
                f"MCP tool call timed out after {timeout_seconds}s"
            ) from exc

        stderr_text = _drain_stderr(proc)
        if isinstance(exc, McpStdioError):
            if stderr_text:
                raise McpStdioError(
                    f"{exc}\nServer stderr: {stderr_text}"
                ) from exc.__cause__
            raise
        raise McpStdioError(
            f"MCP stdio failed: {exc}"
            + (f"\nServer stderr: {stderr_text}" if stderr_text else "")
        ) from exc

    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
