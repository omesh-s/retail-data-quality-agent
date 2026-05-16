"""Abstract metrics data source contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd


class DataSourceConfigurationError(RuntimeError):
    """Raised when a selected provider is missing required configuration."""


@runtime_checkable
class MetricsDataSource(Protocol):
    """Narrow interface: load canonical retail metrics as a DataFrame."""

    @property
    def name(self) -> str:
        """Provider identifier (e.g. ``local_csv``)."""

    def fetch_metrics(self) -> pd.DataFrame:
        """Return metrics with columns expected by the anomaly pipeline."""
