"""Databricks MCP metrics provider (configuration scaffold).

Full MCP query execution is not implemented in this phase. Selecting this provider
with valid configuration will raise a clear error until the integration is completed.
"""

from __future__ import annotations

import logging

import pandas as pd

from config.settings import Settings
from myagent.data_sources.base import DataSourceConfigurationError

logger = logging.getLogger(__name__)


class DatabricksMcpMetricsSource:
    """Fetch metrics via Databricks MCP (future)."""

    name = "databricks_mcp"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _validate_config(self) -> None:
        missing: list[str] = []
        if not self._settings.databricks_mcp_server_url:
            missing.append("DATABRICKS_MCP_SERVER_URL")
        if not self._settings.databricks_metrics_catalog:
            missing.append("DATABRICKS_METRICS_CATALOG")
        if not self._settings.databricks_metrics_schema:
            missing.append("DATABRICKS_METRICS_SCHEMA")
        if not self._settings.databricks_metrics_table:
            missing.append("DATABRICKS_METRICS_TABLE")
        if missing:
            raise DataSourceConfigurationError(
                "RETAIL_DATA_SOURCE=databricks_mcp requires: "
                + ", ".join(missing)
                + ". Use RETAIL_DATA_SOURCE=local_csv for local development."
            )

    def fetch_metrics(self) -> pd.DataFrame:
        self._validate_config()
        logger.warning(
            "Databricks MCP provider selected (server=%s) but query path is not implemented",
            self._settings.databricks_mcp_server_url,
        )
        raise NotImplementedError(
            "Databricks MCP metrics fetch is not implemented yet. "
            "Configure RETAIL_DATA_SOURCE=local_csv or complete the MCP client integration."
        )
