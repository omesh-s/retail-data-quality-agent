"""Local runtime diagnostics for MCP-first ADK setup."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from config.settings import get_settings
from myagent.integrations.mcp_sse_client import diagnose_mcp_sse_call
from myagent.integrations.mcp_stdio_client import diagnose_mcp_stdio_call


def _check_runtime() -> dict:
    s = get_settings()
    checks: list[dict[str, str]] = []

    try:
        s.validate_llm_credentials()
        checks.append(
            {
                "name": "llm_credentials",
                "status": "ok",
                "detail": f"LLM provider {s.llm_provider} appears configured.",
            }
        )
    except ValueError as exc:
        checks.append({"name": "llm_credentials", "status": "fail", "detail": str(exc)})

    if s.wfm_dq_mcp_transport_for_adk == "sse":
        try:
            s.validate_mcp_runtime()
            checks.append(
                {
                    "name": "mcp_server_url",
                    "status": "ok",
                    "detail": (
                        f"Configured MCP SSE endpoint: {s.wfm_dq_mcp_server_url_for_adk} "
                        f"(auth_required={s.wfm_dq_mcp_require_auth_for_sse})"
                    ),
                }
            )
        except ValueError as exc:
            checks.append({"name": "mcp_server_url", "status": "fail", "detail": str(exc)})
    else:
        mcp_path = s.wfm_dq_mcp_server_path_for_adk
        if not mcp_path:
            checks.append(
                {
                    "name": "mcp_server_path",
                    "status": "fail",
                    "detail": "WFM_DQ_MCP_SERVER_PATH_FOR_ADK is not set.",
                }
            )
        elif not Path(mcp_path).is_file():
            checks.append(
                {
                    "name": "mcp_server_path",
                    "status": "fail",
                    "detail": f"MCP server script not found at {mcp_path}",
                }
            )
        else:
            checks.append(
                {
                    "name": "mcp_server_path",
                    "status": "ok",
                    "detail": f"Found MCP server script at {mcp_path}",
                }
            )

    return {
        "status": "ready" if all(c["status"] == "ok" for c in checks) else "not_ready",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose retail MCP-first runtime readiness.")
    parser.add_argument(
        "--diagnose-mcp",
        action="store_true",
        help="Perform a stdio handshake/tool diagnostic against configured MCP server.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="Timeout for --diagnose-mcp.",
    )
    args = parser.parse_args()

    load_dotenv()
    status = _check_runtime()

    if args.diagnose_mcp:
        s = get_settings()
        if s.wfm_dq_mcp_transport_for_adk == "sse":
            if s.wfm_dq_mcp_server_url_for_adk:
                status["mcp_sse_diagnostic"] = diagnose_mcp_sse_call(
                    server_url=s.wfm_dq_mcp_server_url_for_adk,
                    timeout_seconds=args.timeout_seconds,
                    auth_token=s.wfm_dq_mcp_auth_token_for_adk,
                )
            else:
                status["mcp_sse_diagnostic"] = {
                    "ok": False,
                    "error": "MCP server URL is missing; skipped SSE diagnostic.",
                }
        else:
            if (
                s.wfm_dq_mcp_server_path_for_adk
                and Path(s.wfm_dq_mcp_server_path_for_adk).is_file()
            ):
                status["mcp_stdio_diagnostic"] = diagnose_mcp_stdio_call(
                    server_script=s.wfm_dq_mcp_server_path_for_adk,
                    python_executable=s.wfm_dq_mcp_python_for_adk,
                    timeout_seconds=args.timeout_seconds,
                )
            else:
                status["mcp_stdio_diagnostic"] = {
                    "ok": False,
                    "error": "MCP server path is missing or invalid; skipped stdio diagnostic.",
                }

    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
