"""Focused stdio integration tests for the MCP client wrapper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from myagent.integrations import mcp_stdio_client
from myagent.integrations.mcp_stdio_client import (
    McpToolResult,
    call_mcp_tool,
    diagnose_mcp_stdio_call,
)


def _server_script() -> Path:
    return Path(__file__).resolve().parents[2] / "wfm_dq_mcp_server" / "server.py"


def _server_python() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "wfm_dq_mcp_server"
        / ".venv"
        / "Scripts"
        / "python.exe"
    )


def test_stdio_call_get_metric_info():
    script = _server_script()
    py = _server_python()
    if not script.is_file():
        pytest.skip("Paired MCP server.py not found")
    if not py.is_file():
        pytest.skip("Paired MCP server python (.venv) not found")

    result = call_mcp_tool(
        server_script=script,
        tool_name="get_metric_info",
        arguments={"metric_cd": "TEST10_TOT"},
        python_executable=str(py),
        timeout_seconds=60.0,
    )
    assert not result.is_error
    payload = json.loads(result.content_text)
    assert payload["metric_cd"] == "TEST10_TOT"
    assert payload["found"] is True


def test_stdio_diagnostic_helper():
    script = _server_script()
    py = _server_python()
    if not script.is_file():
        pytest.skip("Paired MCP server.py not found")
    if not py.is_file():
        pytest.skip("Paired MCP server python (.venv) not found")

    diag = diagnose_mcp_stdio_call(
        server_script=script,
        python_executable=str(py),
        timeout_seconds=60.0,
    )
    assert "command" in diag
    assert "script" in diag
    assert "cwd" in diag


def test_stdio_diagnostics_toggle_emits_stderr_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    script = tmp_path / "server.py"
    script.write_text("# stub")

    monkeypatch.setenv("MCP_STDIO_DIAGNOSTICS", "true")

    def _fake_run(coro):
        coro.close()
        return McpToolResult(content_text='{"ok":true}', is_error=False)

    monkeypatch.setattr(mcp_stdio_client.asyncio, "run", _fake_run)

    result = call_mcp_tool(
        server_script=script,
        tool_name="get_metric_info",
        arguments={"metric_cd": "TEST10_TOT"},
        timeout_seconds=5.0,
    )
    assert result.content_text == '{"ok":true}'
    stderr = capsys.readouterr().err
    assert "[MCP STDIO]" in stderr
