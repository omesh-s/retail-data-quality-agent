"""Unit tests for MCP SSE client wrapper."""

from __future__ import annotations

from myagent.integrations import mcp_sse_client
from myagent.integrations.mcp_stdio_client import McpToolResult


def test_call_mcp_tool_sse_returns_result_via_asyncio_run(monkeypatch):
    def _fake_run(coro):
        coro.close()
        return McpToolResult(content_text='{"ok":true}', is_error=False)

    monkeypatch.setattr(mcp_sse_client.asyncio, "run", _fake_run)
    result = mcp_sse_client.call_mcp_tool_sse(
        server_url="http://127.0.0.1:8000/sse",
        tool_name="get_metric_info",
        arguments={"metric_cd": "TEST10_TOT"},
        auth_token="token-123",
    )
    assert result.content_text == '{"ok":true}'
    assert not result.is_error


def test_diagnose_mcp_sse_call_reports_failure(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(mcp_sse_client, "call_mcp_tool_sse", _raise)
    diag = mcp_sse_client.diagnose_mcp_sse_call(
        server_url="http://127.0.0.1:8000/sse",
        timeout_seconds=5.0,
        auth_token="token-123",
    )
    assert diag["ok"] is False
    assert "boom" in diag["error"]
