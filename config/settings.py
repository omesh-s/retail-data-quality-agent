# Central settings from environment variables and optional .env file.

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Service host/port, logging, and retail pipeline defaults (no secrets).
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # HTTP API (FastAPI companion service)
    service_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("SERVICE_HOST", "service_host"),
    )
    service_port: int = Field(
        default=8080,
        validation_alias=AliasChoices("SERVICE_PORT", "service_port"),
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "log_level"),
    )
    log_format: Literal["console", "json"] = Field(
        default="console",
        validation_alias=AliasChoices("LOG_FORMAT", "log_format"),
    )
    log_config_file: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("LOG_CONFIG_FILE", "log_config_file"),
    )

    # Retail pipeline (same semantics as previous RETAIL_* env vars)
    retail_metrics_csv: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("RETAIL_METRICS_CSV", "retail_metrics_csv"),
    )
    retail_history_days: int = Field(
        default=30,
        validation_alias=AliasChoices("RETAIL_HISTORY_DAYS", "retail_history_days"),
    )
    retail_z_threshold: float = Field(
        default=4.0,
        validation_alias=AliasChoices("RETAIL_Z_THRESHOLD", "retail_z_threshold"),
    )
    retail_grain_min_distinct: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "RETAIL_GRAIN_MIN_DISTINCT", "retail_grain_min_distinct"
        ),
    )
    retail_grain_min_avg: float | None = Field(
        default=None,
        validation_alias=AliasChoices("RETAIL_GRAIN_MIN_AVG", "retail_grain_min_avg"),
    )
    retail_top_n: int | None = Field(
        default=None,
        validation_alias=AliasChoices("RETAIL_TOP_N", "retail_top_n"),
    )

    @field_validator(
        "retail_metrics_csv",
        "log_config_file",
        "retail_grain_min_avg",
        "retail_top_n",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v: object) -> object:
        # Treat blank env strings as unset for optional path/numeric fields.
        if v is None or v == "":
            return None
        return v


# Cached Settings instance; use get_settings.cache_clear() in tests if env changes.
@lru_cache
def get_settings() -> Settings:
    return Settings()
