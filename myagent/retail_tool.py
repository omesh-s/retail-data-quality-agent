"""ADK tool: MCP-backed adapter for the web chatbot.

This module intentionally stays as a thin adapter layer to reduce migration risk.
It no longer depends on the local CSV pipeline.
"""

from __future__ import annotations

import json
import re

from dotenv import load_dotenv

from myagent.anomaly_to_prompt import format_anomalies_for_llm
from config.settings import get_settings
from myagent.integrations.mcp_stdio_client import McpStdioError, call_mcp_tool

_ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_METRIC = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")
_LOOKBACK = re.compile(r"\b(\d{1,3})\s*day[s]?\s*(?:lookback|window)\b", re.IGNORECASE)
_STORE = re.compile(r"\bstore[_\s-]?(\d+)\b", re.IGNORECASE)
_DEPT = re.compile(r"\b(?:dept|department)\s+([A-Za-z][A-Za-z\s&/-]{1,40})\b", re.IGNORECASE)


def _extract_date(user_message: str, as_of_date: str | None) -> str | None:
    if as_of_date and str(as_of_date).strip():
        return str(as_of_date).strip()
    m = _ISO_DATE.search(user_message or "")
    return m.group(1) if m else None


def _extract_metric_code(user_message: str) -> str | None:
    for match in _METRIC.finditer(user_message or ""):
        code = match.group(1)
        # Exclude common non-metric tokens.
        if code in {"ADK", "MCP", "SQL", "JSON", "CSV"}:
            continue
        return code
    return None


def _extract_lookback_days(user_message: str) -> int | None:
    m = _LOOKBACK.search(user_message or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _extract_store_id(user_message: str) -> int | None:
    m = _STORE.search(user_message or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _extract_dept(user_message: str) -> str | None:
    m = _DEPT.search(user_message or "")
    if not m:
        return None
    return m.group(1).strip()


def _choose_mcp_tool(user_message: str) -> str:
    text = (user_message or "").lower()
    if any(k in text for k in ("roll up", "rollup", "roll-up", "formula", "component metric")):
        return "get_metric_info"
    if any(k in text for k in ("validate", "derived", "mismatch", "expected value", "error percentage")):
        return "validate_derived_metric"
    return "run_full_dq_analysis"


def _mcp_path(settings) -> str:
    path = settings.wfm_dq_mcp_server_path_for_adk
    if not path:
        raise ValueError(
            "MCP server path is not configured. Set WFM_DQ_MCP_SERVER_PATH_FOR_ADK."
        )
    return path


def _compact_summary_payload(tool_name: str, data: dict, user_message: str) -> str:
    if tool_name == "get_metric_info":
        code = data.get("metric_cd", "?")
        if not data.get("found"):
            return f"Metric {code}: not found."
        formula = data.get("formula", "n/a")
        return (
            f"Metric {code}\n"
            f"- dept={data.get('dept_desc', 'n/a')}\n"
            f"- wfm_required={data.get('is_wfm_required', 'n/a')}\n"
            f"- derived={data.get('is_derived_rollup', False)}\n"
            f"- formula={formula}"
        )

    if tool_name == "validate_derived_metric":
        metric_cd = data.get("metric_cd", "?")
        dept_desc = data.get("dept_desc", "all")
        check_date = data.get("check_date", "n/a")
        rows = data.get("store_results", []) or []
        mismatches = [r for r in rows if not bool(r.get("match"))]
        if not mismatches:
            return (
                f"Derived validation: {metric_cd} ({dept_desc}) on {check_date}\n"
                "No mismatches found."
            )

        anomalies = []
        for r in mismatches:
            anomalies.append(
                {
                    "issue_type": "Derived Metric Mismatch",
                    "severity": "High",
                    "metric_cd": metric_cd,
                    "dept_desc": dept_desc,
                    "store_id": r.get("store_id"),
                    "csv_value": r.get("csv_value"),
                    "expected_value": r.get("expected_value"),
                    "error_pct": r.get("error_pct"),
                    "component_metric_codes": data.get("component_metric_codes", []),
                }
            )
        block = format_anomalies_for_llm(anomalies)
        return (
            f"Derived validation: {metric_cd} ({dept_desc}) on {check_date}\n"
            f"Mismatches={len(mismatches)}\n\n{block}"
        )

    # Default: run_full_dq_analysis
    anomalies = data.get("anomaly_list", []) or []
    block = format_anomalies_for_llm(anomalies)
    return (
        f"DQ analysis {data.get('check_date', 'n/a')}: "
        f"total={data.get('total_anomalies', len(anomalies))}, "
        f"wfm_required={data.get('wfm_required_count', 'n/a')}\n\n{block}"
    )


def run_retail_data_quality_analysis(
    user_message: str = "",
    as_of_date: str | None = None,
) -> str:
    """Run MCP-backed analysis and return compact, LLM-ready context.

    This adapter chooses a targeted MCP tool when possible:
    - `get_metric_info` for metadata/formula lookup questions
    - `validate_derived_metric` for derived validation questions
    - `run_full_dq_analysis` for broad/other DQ analysis
    """
    load_dotenv()
    s = get_settings()
    text = user_message or ""
    tool_name = _choose_mcp_tool(text)
    check_date = _extract_date(text, as_of_date)
    metric_cd = _extract_metric_code(text)
    dept_desc = _extract_dept(text)
    store_id = _extract_store_id(text)
    lookback_days = _extract_lookback_days(text) or 14

    args: dict = {}
    if tool_name == "get_metric_info":
        if not metric_cd:
            tool_name = "run_full_dq_analysis"
        else:
            args = {"metric_cd": metric_cd}
    if tool_name == "validate_derived_metric":
        if not (metric_cd and check_date):
            tool_name = "run_full_dq_analysis"
        else:
            args = {"metric_cd": metric_cd, "check_date": check_date}
            if dept_desc:
                args["dept_desc"] = dept_desc
            if store_id is not None:
                args["store_id"] = store_id
    if tool_name == "run_full_dq_analysis":
        args = {"lookback_days": lookback_days}
        if check_date:
            args["check_date"] = check_date
        if dept_desc:
            args["dept_desc"] = dept_desc

    path = _mcp_path(s)
    py = s.wfm_dq_mcp_python_for_adk
    timeout = s.wfm_dq_mcp_server_timeout_for_adk

    try:
        response = call_mcp_tool(
            server_script=path,
            tool_name=tool_name,
            arguments=args,
            timeout_seconds=timeout,
            python_executable=py,
        )
        if response.is_error:
            raise RuntimeError(response.content_text or "unknown MCP tool error")
        data = json.loads(response.content_text)
        return _compact_summary_payload(tool_name, data, text)
    except (McpStdioError, json.JSONDecodeError, RuntimeError):
        # Graceful fallback: broad analysis tool.
        fallback_args = {"lookback_days": lookback_days}
        if check_date:
            fallback_args["check_date"] = check_date
        if dept_desc:
            fallback_args["dept_desc"] = dept_desc
        response = call_mcp_tool(
            server_script=path,
            tool_name="run_full_dq_analysis",
            arguments=fallback_args,
            timeout_seconds=timeout,
            python_executable=py,
        )
        if response.is_error:
            return f"MCP analysis failed: {response.content_text}"
        data = json.loads(response.content_text)
        return _compact_summary_payload("run_full_dq_analysis", data, text)
