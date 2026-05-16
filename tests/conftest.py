"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "retail_data_quality_sim.csv"


@pytest.fixture
def sample_csv_path() -> Path:
    return DEFAULT_CSV
