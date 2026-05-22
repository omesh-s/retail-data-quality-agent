"""Local CSV metrics provider (default for development)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from config.settings import Settings
from myagent.data_loading import load_metrics_file
from myagent.pipeline import DEFAULT_CSV

logger = logging.getLogger(__name__)


class LocalCsvMetricsSource:
    """Load retail metrics from a CSV file on disk."""

    name = "local_csv"

    def __init__(self, settings: Settings, *, csv_path: Path | None = None) -> None:
        self._settings = settings
        self._csv_path = csv_path

    def fetch_metrics(self) -> pd.DataFrame:
        path = self._csv_path or self._settings.retail_metrics_csv or DEFAULT_CSV
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Metrics CSV not found: {path}")
        logger.info("Loading metrics from local CSV: %s", path)
        return load_metrics_file(path, self._settings)
