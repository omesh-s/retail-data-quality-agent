"""Efficient metrics file loading (CSV / Parquet) with optional chunked reads."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from config.schema_aliases import apply_schema_normalization
from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_CSV_DTYPES = {
    "Storeid": "Int64",
    "Deptname": "string",
    "metriccode": "string",
    "metricvalue": "float64",
}


def load_metrics_file(
    path: str | Path,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Load a metrics file and return a normalized DataFrame."""
    s = settings or get_settings()
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Metrics file not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".parquet":
        raw = _read_parquet(p, s)
    else:
        raw = _read_csv(p, s)

    return apply_schema_normalization(
        raw,
        profile=s.data_schema_profile,
        map_file=s.data_schema_map_file,
    )


def _read_csv(path: Path, settings: Settings) -> pd.DataFrame:
    chunk_size = settings.data_read_chunk_size
    read_kwargs: dict = {}
    if settings.data_use_pyarrow:
        read_kwargs["engine"] = "pyarrow"
    else:
        read_kwargs["low_memory"] = False

    if chunk_size and chunk_size > 0:
        parts: list[pd.DataFrame] = []
        for chunk in pd.read_csv(path, chunksize=chunk_size, **read_kwargs):
            parts.append(chunk)
        if not parts:
            return pd.DataFrame()
        raw = pd.concat(parts, ignore_index=True)
        logger.info("Loaded CSV in %s chunks (%s rows)", len(parts), len(raw))
    else:
        raw = pd.read_csv(path, **read_kwargs)
        logger.info("Loaded CSV (%s rows)", len(raw))

    for col, dtype in _CSV_DTYPES.items():
        if col in raw.columns:
            try:
                raw[col] = raw[col].astype(dtype)
            except (TypeError, ValueError):
                pass
    return raw


def _read_parquet(path: Path, settings: Settings) -> pd.DataFrame:
    try:
        if settings.data_use_pyarrow:
            raw = pd.read_parquet(path, engine="pyarrow")
        else:
            raw = pd.read_parquet(path)
    except ImportError as exc:
        raise ImportError(
            "Parquet support requires pyarrow. Install pyarrow or use CSV."
        ) from exc
    logger.info("Loaded Parquet (%s rows)", len(raw))
    return raw
