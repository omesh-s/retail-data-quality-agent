"""Shared metrics fetch + anomaly pipeline for all entry points."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from config.settings import Settings, get_settings
from myagent.data_sources.base import MetricsDataSource
from myagent.data_sources.factory import DataSourceKind, get_metrics_data_source
from myagent.pipeline import OUTPUT_DIR, PipelineResult, run_detection_pipeline_from_dataframe

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnomalyPipelineRunResult:
    """Provider-backed pipeline execution (detectors + enrichment + prompt)."""

    pipeline: PipelineResult
    data_source: str


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
    """
    s = settings or get_settings()
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
