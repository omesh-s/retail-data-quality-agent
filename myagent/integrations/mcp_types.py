"""Typed helpers for Databricks MCP JSON-RPC requests and responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class McpToolsCallRequest:
    """JSON-RPC 2.0 tools/call payload."""

    tool_name: str
    query: str
    request_id: int = 1

    def to_payload(self) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {
                "name": self.tool_name,
                "arguments": {"query": self.query},
            },
        }


@dataclass
class McpToolsCallResponse:
    """Parsed MCP HTTP JSON body."""

    result: Any = None
    error_message: str | None = None

    @classmethod
    def from_http_json(cls, body: dict[str, Any]) -> McpToolsCallResponse:
        if "error" in body:
            err = body["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            return cls(error_message=str(msg))
        return cls(result=body.get("result", body))

    @property
    def ok(self) -> bool:
        return self.error_message is None
