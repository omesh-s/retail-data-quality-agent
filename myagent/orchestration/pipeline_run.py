"""Shared metrics fetch + anomaly pipeline for all entry points."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import Settings, get_settings
from myagent.data_sources.base import MetricsDataSource
from myagent.data_sources.factory import DataSourceKind, get_metrics_data_source
from myagent.integrations.mcp_stdio_client import McpStdioError, call_mcp_tool
from myagent.pipeline import (
    OUTPUT_DIR,
    PipelineResult,
    build_result_from_preanalyzed_anomalies,
    run_detection_pipeline_from_dataframe,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnomalyPipelineRunResult:
    """Provider-backed pipeline execution (detectors + enrichment + prompt)."""

    pipeline: PipelineResult
    data_source: str


# ---------------------------------------------------------------------------
# Metrics-based providers (local_csv, databricks_mcp)
# ---------------------------------------------------------------------------

def resolve_metrics_provider(
    settings: Settings,
    *,
    data_source: DataSourceKind | str | None = None,
    csv_path: str | Path | None = None,
) -> MetricsDataSource:
    """Resolve the metrics provider.

    When *csv_path* is set, always use ``local_csv`` with that file (explicit override).
    Otherwise use *data_source* or ``RETAIL_DATA_SOURCE`` from settings.
    """
    if csv_path is not None:
        logger.info("Using local_csv override path: %s", csv_path)
        return get_metrics_data_source(
            settings, source="local_csv", csv_path=str(csv_path)
        )
    return get_metrics_data_source(settings, source=data_source)


# ---------------------------------------------------------------------------
# MCP server mode — pre-analyzed anomalies, skip local detection
# ---------------------------------------------------------------------------

_SEVERITY_TO_IMPACT: dict[str, float] = {"High": 0.85, "Medium": 0.50, "Low": 0.20}


def _map_mcp_anomaly(rec: dict[str, Any]) -> dict[str, Any]:
    """Map MCP server anomaly fields to the project's canonical format."""
    severity = rec.get("severity", "Low")
    impact = _SEVERITY_TO_IMPACT.get(severity, 0.20)
    return {
        "storeid": rec.get("store_id"),
        "deptname": rec.get("dept_desc"),
        "metriccode": rec.get("metric_cd"),
        "metricvalue": rec.get("metric_value"),
        "date_or_range": rec.get("check_date"),
        "issue_type": rec.get("issue_type"),
        "severity": severity,
        "impact_score": round(impact, 2),
        "estimated_revenue_at_risk": None,
        "customer_impact": severity if severity != "Low" else None,
        "operational_risk": severity if severity != "Low" else None,
        "details": rec.get("details", ""),
        "is_wfm_required": rec.get("is_wfm_required"),
        "z_score": rec.get("z_score"),
        "historical_mean": rec.get("historical_mean"),
    }


def _run_mcp_server_pipeline(
    settings: Settings,
    *,
    as_of_date: str | None = None,
    history_days: int | None = None,
    top_n: int | None = None,
    save_exports: bool = True,
    output_dir: str | Path | None = None,
) -> AnomalyPipelineRunResult:
    """Run anomaly pipeline via MCP server (skips local detection/enrichment)."""
    if not settings.wfm_dq_mcp_server_path:
        raise ValueError(
            "RETAIL_DATA_SOURCE=mcp_server requires WFM_DQ_MCP_SERVER_PATH "
            "(absolute path to the MCP server script, e.g. /path/to/server.py)."
        )

    tool_args: dict[str, Any] = {}
    if as_of_date and str(as_of_date).strip():
        tool_args["check_date"] = str(as_of_date).strip()
    lookback = history_days if history_days is not None else settings.retail_history_days
    tool_args["lookback_days"] = lookback

    logger.info("Calling MCP server run_full_dq_analysis: %s", tool_args)

    result = call_mcp_tool(
        server_script=settings.wfm_dq_mcp_server_path,
        tool_name="run_full_dq_analysis",
        arguments=tool_args,
        timeout_seconds=settings.wfm_dq_mcp_timeout_seconds,
    )

    if result.is_error:
        raise RuntimeError(f"MCP server reported error: {result.content_text}")

    try:
        data = json.loads(result.content_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse MCP server response as JSON: {exc}"
        ) from exc

    mcp_anomalies = data.get("anomaly_list", [])
    resolved_date = data.get("check_date", as_of_date or "unknown")

    logger.info(
        "MCP server returned %d anomalies for %s", len(mcp_anomalies), resolved_date
    )

    anomalies = [_map_mcp_anomaly(a) for a in mcp_anomalies]
    effective_top_n = top_n if top_n is not None else settings.retail_top_n

    pipeline = build_result_from_preanalyzed_anomalies(
        anomalies,
        as_of_str=resolved_date,
        top_n=effective_top_n,
        save_exports=save_exports,
        output_dir=output_dir or OUTPUT_DIR,
    )
    return AnomalyPipelineRunResult(pipeline=pipeline, data_source="mcp_server")


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def run_anomaly_pipeline(
    *,
    as_of_date: str | None = None,
    user_message: str = "",
    settings: Settings | None = None,
    data_source: DataSourceKind | str | None = None,
    csv_path: str | Path | None = None,
    history_days: int | None = None,
    z_threshold: float | None = None,
    grain_min_distinct_days: int | None = None,
    grain_min_avg: float | None = None,
    top_n: int | None = None,
    save_exports: bool = True,
    output_dir: str | Path | None = None,
) -> AnomalyPipelineRunResult:
    """Fetch metrics via the data-source layer and run the shared anomaly pipeline.

    Used by ``run_day.py``, the ADK tool, daily report, and HTTP triggers.

    When ``RETAIL_DATA_SOURCE=mcp_server``, detection and enrichment are
    performed by the remote MCP server; the local pipeline only handles
    formatting and export.
    """
    s = settings or get_settings()

    effective_source = (data_source or s.retail_data_source).strip().lower()
    if csv_path:
        effective_source = "local_csv"

    # MCP server mode — bypass local detection entirely
    if effective_source == "mcp_server":
        return _run_mcp_server_pipeline(
            s,
            as_of_date=as_of_date,
            history_days=history_days,
            top_n=top_n,
            save_exports=save_exports,
            output_dir=output_dir,
        )

    # Standard mode — fetch raw metrics, run local detectors + enrichment
    provider = resolve_metrics_provider(
        s, data_source=data_source, csv_path=csv_path
    )
    logger.info("Anomaly pipeline using data source: %s", provider.name)

    metrics_df = provider.fetch_metrics()

    pipeline = run_detection_pipeline_from_dataframe(
        metrics_df,
        as_of_date=as_of_date,
        user_message=user_message,
        history_days=history_days if history_days is not None else s.retail_history_days,
        z_threshold=z_threshold if z_threshold is not None else s.retail_z_threshold,
        grain_min_distinct_days=(
            grain_min_distinct_days
            if grain_min_distinct_days is not None
            else s.retail_grain_min_distinct
        ),
        grain_min_avg=grain_min_avg if grain_min_avg is not None else s.retail_grain_min_avg,
        top_n=top_n if top_n is not None else s.retail_top_n,
        save_exports=save_exports,
        output_dir=output_dir or OUTPUT_DIR,
    )

    return AnomalyPipelineRunResult(pipeline=pipeline, data_source=provider.name)
