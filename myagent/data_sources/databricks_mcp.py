"""Databricks MCP metrics provider."""

from __future__ import annotations

import logging

import pandas as pd

from config.settings import Settings
from myagent.anomaly_detector import normalize_metrics_dataframe
from myagent.data_sources.base import DataSourceConfigurationError
from myagent.integrations.databricks_mcp_client import (
    DatabricksMcpClient,
    DatabricksMcpClientError,
)

logger = logging.getLogger(__name__)


class DatabricksMcpMetricsSource:
    """Fetch retail metrics by executing SQL through a Databricks MCP server."""

    name = "databricks_mcp"

    def __init__(
        self,
        settings: Settings,
        *,
        client: DatabricksMcpClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

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

    def _build_sql(self) -> str:
        if self._settings.databricks_metrics_sql:
            return self._settings.databricks_metrics_sql.strip()
        cat = self._settings.databricks_metrics_catalog
        schema = self._settings.databricks_metrics_schema
        table = self._settings.databricks_metrics_table
        return f"SELECT * FROM `{cat}`.`{schema}`.`{table}`"

    def fetch_metrics(self) -> pd.DataFrame:
        self._validate_config()
        sql = self._build_sql()
        client = self._client or DatabricksMcpClient(self._settings)
        try:
            raw = client.execute_sql(sql)
        except DatabricksMcpClientError as exc:
            raise RuntimeError(f"Databricks MCP metrics fetch failed: {exc}") from exc

        if raw.empty:
            logger.warning("Databricks MCP returned an empty metrics frame")
            return normalize_metrics_dataframe(raw)

        normalized = normalize_metrics_dataframe(raw)
        logger.info(
            "Databricks MCP loaded %s rows (%s .. %s)",
            len(normalized),
            normalized["metricdate"].min(),
            normalized["metricdate"].max(),
        )
        return normalized
