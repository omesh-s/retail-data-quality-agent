"""Resolve configured metrics data source."""

from __future__ import annotations

from typing import Literal

from config.settings import Settings, get_settings
from myagent.data_sources.databricks_mcp import DatabricksMcpMetricsSource
from myagent.data_sources.local_csv import LocalCsvMetricsSource

DataSourceKind = Literal["local_csv", "databricks_mcp"]

_SUPPORTED: tuple[DataSourceKind, ...] = ("local_csv", "databricks_mcp")


def get_metrics_data_source(
    settings: Settings | None = None,
    *,
    source: DataSourceKind | str | None = None,
    csv_path: str | None = None,
) -> LocalCsvMetricsSource | DatabricksMcpMetricsSource:
    """Return the configured :class:`MetricsDataSource` implementation.

    Args:
        settings: Optional settings instance (defaults to cached ``get_settings()``).
        source: Override ``RETAIL_DATA_SOURCE`` for this call.
        csv_path: Optional CSV path override (``local_csv`` only).
    """
    s = settings or get_settings()
    kind = (source or s.retail_data_source).strip().lower()
    if kind not in _SUPPORTED:
        raise ValueError(
            f"Unknown data source {kind!r}. Supported: {', '.join(_SUPPORTED)}"
        )
    if kind == "local_csv":
        from pathlib import Path

        path = Path(csv_path) if csv_path else None
        return LocalCsvMetricsSource(s, csv_path=path)
    return DatabricksMcpMetricsSource(s)
