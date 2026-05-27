# ADK root agent for MCP-first retail data quality workflows.
#
# ADK discovery
# -------------
# ``adk web .`` scans for a Python package exporting ``root_agent``.
# ``myagent/__init__.py`` re-exports it from this module.
# The ADK UI shows an app named **myagent** with the agent
# **retail_data_quality_agent**.
#
# Tools registered
# ----------------
# 1. FunctionTool(run_retail_data_quality_analysis) — always present.
#    MCP-backed adapter that routes to backend tools and returns compact context.
#
# 2. McpToolset (external DQ MCP server) — present only when
#    ``WFM_DQ_MCP_SERVER_PATH_FOR_ADK`` is set and the script exists.
#    May expose tools like:
#      - get_available_dates
#      - run_full_dq_analysis
#      - get_metric_info
#      - validate_derived_metric
#    The exact tool set depends on the external server implementation.
#
# Configuration
# -------------
# ``LLM_MODEL``                         → Gemini model for the agent
# ``WFM_DQ_MCP_TRANSPORT_FOR_ADK``      → stdio (local) or sse (remote)
# ``WFM_DQ_MCP_SERVER_PATH_FOR_ADK``    → path to MCP server script for stdio mode
# ``WFM_DQ_MCP_SERVER_URL_FOR_ADK``     → MCP SSE endpoint for remote mode
# ``WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK``     → optional bearer token for remote SSE mode
# ``WFM_DQ_MCP_PYTHON_FOR_ADK``         → Python interpreter for the MCP server
#                                          (auto-detects venv in server dir if unset)
# ``WFM_DQ_MCP_SERVER_TIMEOUT_FOR_ADK`` → stdio connection timeout (default 90s)

from __future__ import annotations

import logging
import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools.function_tool import FunctionTool

from app.logging_setup import configure_logging
from config.settings import get_settings
from myagent.retail_tool import run_retail_data_quality_analysis

configure_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def _default_adk_model() -> str:
    try:
        return get_settings().llm_model
    except Exception:
        return "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# MCP server Python resolver
# ---------------------------------------------------------------------------

_VENV_CANDIDATES = (
    # Windows
    (".venv", "Scripts", "python.exe"),
    ("venv", "Scripts", "python.exe"),
    # Unix / macOS
    (".venv", "bin", "python"),
    ("venv", "bin", "python"),
)


def _resolve_mcp_python(server_dir: Path, explicit: str | None) -> str:
    """Determine the Python interpreter to use for the MCP server.

    Priority:
      1. ``WFM_DQ_MCP_PYTHON_FOR_ADK`` (explicit override)
      2. A venv found in the server directory
      3. ``sys.executable`` (current interpreter — may lack server deps)
    """
    if explicit:
        p = Path(explicit)
        if p.is_file():
            logger.info("MCP Python (explicit): %s", p)
            return str(p)
        logger.warning(
            "WFM_DQ_MCP_PYTHON_FOR_ADK=%s not found; trying venv auto-detect",
            explicit,
        )

    for parts in _VENV_CANDIDATES:
        candidate = server_dir.joinpath(*parts)
        if candidate.is_file():
            logger.info("MCP Python (auto-detected venv): %s", candidate)
            return str(candidate)

    logger.warning(
        "No venv found in %s — falling back to sys.executable (%s). "
        "If the MCP server has its own dependencies (e.g. databricks-sql-connector), "
        "set WFM_DQ_MCP_PYTHON_FOR_ADK to a Python that has them installed.",
        server_dir,
        sys.executable,
    )
    return sys.executable


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _build_mcp_toolset():
    """Create an McpToolset for WFM DQ MCP server (stdio or sse)."""
    try:
        settings = get_settings()
        transport = settings.wfm_dq_mcp_transport_for_adk
        timeout = settings.wfm_dq_mcp_server_timeout_for_adk

        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

        if transport == "sse":
            server_url = settings.wfm_dq_mcp_server_url_for_adk
            if not server_url:
                logger.warning(
                    "WFM_DQ_MCP_TRANSPORT_FOR_ADK=sse but WFM_DQ_MCP_SERVER_URL_FOR_ADK is not "
                    "set; MCP toolset disabled."
                )
                return None
            headers = None
            if settings.wfm_dq_mcp_auth_token_for_adk:
                headers = {"Authorization": f"Bearer {settings.wfm_dq_mcp_auth_token_for_adk}"}

            from google.adk.tools.mcp_tool.mcp_toolset import SseConnectionParams

            toolset = McpToolset(
                connection_params=SseConnectionParams(
                    url=server_url,
                    headers=headers,
                    timeout=timeout,
                    sse_read_timeout=timeout,
                )
            )
            logger.info(
                "ADK MCP toolset created (sse): url=%s auth=%s timeout=%ss",
                server_url,
                "enabled" if headers else "disabled",
                timeout,
            )
            return toolset

        mcp_path = settings.wfm_dq_mcp_server_path_for_adk
        if not mcp_path:
            logger.debug("WFM_DQ_MCP_SERVER_PATH_FOR_ADK not set; MCP toolset disabled")
            return None
        script = Path(mcp_path).resolve()
        if not script.is_file():
            logger.warning(
                "WFM_DQ_MCP_SERVER_PATH_FOR_ADK=%s does not exist; ADK will run without MCP tools.",
                mcp_path,
            )
            return None
        python_cmd = _resolve_mcp_python(script.parent, settings.wfm_dq_mcp_python_for_adk)

        from google.adk.tools.mcp_tool.mcp_toolset import (
            StdioConnectionParams,
            StdioServerParameters,
        )

        toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=python_cmd,
                    args=[str(script)],
                    cwd=str(script.parent),
                ),
                timeout=timeout,
            ),
        )
        logger.info(
            "ADK MCP toolset created (stdio): script=%s python=%s timeout=%ss",
            script,
            python_cmd,
            timeout,
        )
        return toolset

    except Exception as exc:
        logger.warning(
            "Failed to configure MCP toolset for ADK (%s: %s); running with pipeline tool only.",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return None


def _build_tools() -> list:
    """Assemble tool list: MCP-backed FunctionTool + optional direct MCP toolset."""
    tools: list = [FunctionTool(run_retail_data_quality_analysis)]
    mcp = _build_mcp_toolset()
    if mcp is not None:
        tools.append(mcp)

    logger.info(
        "ADK tools registered: %s",
        [type(t).__name__ for t in tools],
    )
    return tools


# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------

_BASE_INSTRUCTION = """\
You are a Retail Data Quality Analyst agent. Your job is to orchestrate MCP \
tools and deliver concise, business-relevant summaries.

## Core rules
- ALWAYS call a tool before answering any data-quality question.
- Tool output is the sole source of truth. Never invent anomalies, \
severity levels, or data not present in tool results.
- Do not explain detection algorithms or repeat raw field names verbatim.

## Tool selection
- ``run_retail_data_quality_analysis``: MCP-backed adapter for broad and \
targeted analysis. Pass ``user_message`` and optional ``as_of_date``.
- Prefer targeted tools for targeted questions:
  - continuity/missing data -> continuity findings from MCP output
  - negative outliers -> negative findings from MCP output
  - derived validation -> use MCP validate tool when available

## How to interpret tool output

### Continuity gaps / missing data
- A metric missing 7+ consecutive days at ONE store is a localized issue.
- The SAME metric missing across MULTIPLE stores in the same date window \
is a systemic or upstream feed failure — flag it as higher concern.
- If tool output contains ``continuity_scope``, use it directly \
(isolated / multi_store / systemic).
- If tool output contains ``affected_store_count``, cite the blast radius.
- If these fields are absent, infer scope from repeated patterns if clear; \
otherwise report each gap individually without over-claiming.

### Negative values
- Small negatives (e.g. -5, -10) CAN be legitimate operational reversals \
in retail (bulk order cancellations, correction flows).
- Large negatives (e.g. -1000) are genuine data quality concerns.
- Do NOT overstate every negative as "data corruption."
- If ``negative_magnitude``, ``historical_ratio``, or ``severity_reason`` \
are present, use them to calibrate your language.
- Separate likely operational reversals from suspicious large outliers.

### Derived metric mismatches
- These are HIGHEST PRIORITY when flagged. A derived total not matching \
its component sum indicates a calculation or ETL defect.
- If ``csv_value``, ``expected_value``, ``error_pct``, and \
``component_metric_codes`` are present, cite them with exact numbers.
- If a ``validate_derived_metric`` tool is available and the user asks \
about a specific formula, prefer that targeted tool over broad analysis.

### Priority and severity
- If ``priority`` is present, use it for ordering (lower = more important).
- ``severity`` (High/Medium/Low) is the main business label.
- ``severity_reason`` explains why in one phrase — use it if present.
- If ``scope_summary`` is present, mention the aggregate breakdown briefly.

## Response format

**For broad daily analysis:**
One-sentence health assessment, then 3-5 bullets max:
- Lead with highest priority / severity finding
- Each bullet: severity, issue type, metric, store(s), one key fact
- Group related findings (e.g. "3 stores affected" not 3 separate bullets)
- Mention blast radius for multi-store/systemic issues
- Omit Low-severity unless nothing else exists

**For specific questions** (continuity, negatives, derived checks):
Answer the question directly and concisely. Include only findings \
relevant to what was asked. Do not pad with unrelated issue types.

**For derived metric validation:**
Show a compact result: metric formula, mismatched stores, csv vs expected \
values, error percentage. Skip stores that match.

Stay concise. No filler. No generic phrases like "overall there are some \
anomalies." Lead with what matters most.
"""

_MCP_INSTRUCTION_ADDENDUM = """
## MCP tools (external DQ server)
When an external MCP server is connected, additional tools may be available:
- ``get_available_dates`` — date range in the source table.
- ``run_full_dq_analysis(check_date, lookback_days, dept_desc)`` — full \
DQ rule execution on production data. Returns richer fields including \
``priority``, ``continuity_scope``, ``scope_summary``, and \
``severity_reason``.
- ``get_metric_info(metric_cd)`` — metric metadata and derived formulas.
- ``validate_derived_metric(metric_cd, check_date, dept_desc, store_id)`` \
— targeted derived formula check. Prefer this for specific formula \
validation questions.

**Routing guidance:**
- Use MCP tools for production / Databricks data questions.
- Do NOT invent local detector logic; MCP output is source of truth.
- For "validate this derived metric" questions, use \
``validate_derived_metric`` if available. If unavailable, fall back to \
``run_full_dq_analysis`` and filter for derived mismatch findings.
- For "is this 7-day drop isolated or systemic" questions, use \
``run_full_dq_analysis`` and focus on continuity findings.
- For "show negative outliers" questions, use ``run_full_dq_analysis`` \
and focus on negative outlier findings.
"""


def _build_instruction() -> str:
    """Build agent instruction, appending MCP guidance if MCP tools are configured."""
    try:
        settings = get_settings()
        if settings.wfm_dq_mcp_transport_for_adk == "sse":
            if settings.wfm_dq_mcp_server_url_for_adk:
                return _BASE_INSTRUCTION + _MCP_INSTRUCTION_ADDENDUM
        elif settings.wfm_dq_mcp_server_path_for_adk:
            script = Path(settings.wfm_dq_mcp_server_path_for_adk)
            if script.exists():
                return _BASE_INSTRUCTION + _MCP_INSTRUCTION_ADDENDUM
    except Exception:
        pass
    return _BASE_INSTRUCTION


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

root_agent = Agent(
    name="retail_data_quality_agent",
    model=_default_adk_model(),
    description="Analyzes retail metric anomalies and summarizes data quality issues.",
    tools=_build_tools(),
    instruction=_build_instruction(),
)
