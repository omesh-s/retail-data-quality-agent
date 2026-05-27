"""Paired local runner for ADK agent + MCP backend."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from config.settings import get_settings

_VENV_CANDIDATES = (
    (".venv", "Scripts", "python.exe"),
    ("venv", "Scripts", "python.exe"),
    (".venv", "bin", "python"),
    ("venv", "bin", "python"),
)


def _resolve_mcp_python(server_dir: Path, explicit: str | None) -> str:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return str(p)
    for parts in _VENV_CANDIDATES:
        candidate = server_dir.joinpath(*parts)
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def _run_backend_env_check(server_python: str, server_script: str) -> int:
    proc = subprocess.run([server_python, server_script, "--check-env"], check=False)
    return proc.returncode


def _start_backend_sse(server_python: str, server_script: str, server_url: str) -> subprocess.Popen:
    parsed = urlparse(server_url)
    env = dict(os.environ)
    if parsed.hostname:
        env["WFM_DQ_MCP_BIND_HOST"] = parsed.hostname
    if parsed.port:
        env["WFM_DQ_MCP_BIND_PORT"] = str(parsed.port)
    return subprocess.Popen([server_python, server_script, "--sse"], env=env)


def _run_adk_web() -> int:
    venv_adk = Path(sys.executable).with_name("adk.exe")
    if venv_adk.is_file():
        return subprocess.run([str(venv_adk), "web", "."], check=False).returncode
    try:
        return subprocess.run(["adk", "web", "."], check=False).returncode
    except FileNotFoundError:
        return subprocess.run(
            [sys.executable, "-m", "google.adk.cli", "web", "."],
            check=False,
        ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run paired ADK + MCP local profile.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("up", help="Start paired local profile.")
    up.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=None,
        help="Override MCP transport for this run.",
    )

    sub.add_parser("check", help="Validate paired runtime prerequisites.")

    args = parser.parse_args()
    load_dotenv()
    s = get_settings()

    if args.cmd == "check":
        try:
            s.validate_llm_credentials()
            print("[ok] LLM credentials configured")
        except ValueError as exc:
            print(f"[fail] LLM credentials: {exc}")
            return 1

        try:
            s.validate_mcp_runtime()
            print(f"[ok] MCP transport configuration valid ({s.wfm_dq_mcp_transport_for_adk})")
        except ValueError as exc:
            print(f"[fail] MCP runtime: {exc}")
            return 1

        if s.wfm_dq_mcp_server_path_for_adk and Path(s.wfm_dq_mcp_server_path_for_adk).is_file():
            server_script = s.wfm_dq_mcp_server_path_for_adk
            server_python = _resolve_mcp_python(
                Path(server_script).parent,
                s.wfm_dq_mcp_python_for_adk,
            )
            rc = _run_backend_env_check(server_python, server_script)
            if rc != 0:
                print("[fail] MCP backend --check-env failed")
                return rc
            print("[ok] MCP backend --check-env succeeded")
        else:
            print("[warn] MCP script path unavailable; skipped backend --check-env")
        return 0

    transport = args.transport or s.wfm_dq_mcp_transport_for_adk
    backend_proc: subprocess.Popen | None = None
    try:
        if transport == "sse":
            if not s.wfm_dq_mcp_server_path_for_adk:
                print("[fail] WFM_DQ_MCP_SERVER_PATH_FOR_ADK is required to launch local backend.")
                return 2
            if not s.wfm_dq_mcp_server_url_for_adk:
                print("[fail] WFM_DQ_MCP_SERVER_URL_FOR_ADK is required for SSE paired run.")
                return 2
            server_script = s.wfm_dq_mcp_server_path_for_adk
            if not Path(server_script).is_file():
                print(f"[fail] MCP server script not found: {server_script}")
                return 2
            server_python = _resolve_mcp_python(
                Path(server_script).parent,
                s.wfm_dq_mcp_python_for_adk,
            )
            print(f"[info] Starting MCP backend in SSE mode at {s.wfm_dq_mcp_server_url_for_adk}")
            backend_proc = _start_backend_sse(
                server_python=server_python,
                server_script=server_script,
                server_url=s.wfm_dq_mcp_server_url_for_adk,
            )
        else:
            print("[info] Running in stdio mode; backend process is spawned per tool call.")

        print("[info] Starting ADK web ...")
        return _run_adk_web()
    finally:
        if backend_proc and backend_proc.poll() is None:
            print("[info] Stopping MCP backend process.")
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
