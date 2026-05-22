# Central settings from environment variables and optional .env file.

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProvider = Literal["googlegenai", "openai", "anthropic", "litellm"]
DataSourceKind = Literal["local_csv", "databricks_mcp"]
LogFormat = Literal["console", "json"]


class Settings(BaseSettings):
    """Single source of truth for service, pipeline, data, Slack, and LLM config."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    llm_provider: LlmProvider = Field(
        default="googlegenai",
        validation_alias=AliasChoices("LLM_PROVIDER", "llm_provider"),
    )
    llm_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("LLM_MODEL", "llm_model"),
    )
    google_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_API_KEY", "google_api_key"),
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"),
    )
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key"),
    )
    litellm_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LITELLM_API_BASE", "litellm_api_base"),
    )
    litellm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LITELLM_API_KEY", "litellm_api_key"),
    )

    # --- HTTP service ---
    service_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("SERVICE_HOST", "service_host"),
    )
    service_port: int = Field(
        default=8080,
        validation_alias=AliasChoices("SERVICE_PORT", "service_port"),
    )

    # --- Logging ---
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "log_level"),
    )
    log_format: LogFormat = Field(
        default="console",
        validation_alias=AliasChoices("LOG_FORMAT", "log_format"),
    )
    log_config_file: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("LOG_CONFIG_FILE", "log_config_file"),
    )

    # --- Data source ---
    retail_data_source: DataSourceKind = Field(
        default="local_csv",
        validation_alias=AliasChoices("RETAIL_DATA_SOURCE", "retail_data_source"),
    )
    retail_metrics_csv: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("RETAIL_METRICS_CSV", "retail_metrics_csv"),
    )

    # --- Pipeline defaults ---
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

    # --- Schema / performance ---
    data_schema_profile: str = Field(
        default="retail_default",
        validation_alias=AliasChoices("DATA_SCHEMA_PROFILE", "data_schema_profile"),
    )
    data_schema_map_file: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("DATA_SCHEMA_MAP_FILE", "data_schema_map_file"),
    )
    data_read_chunk_size: int | None = Field(
        default=None,
        validation_alias=AliasChoices("DATA_READ_CHUNK_SIZE", "data_read_chunk_size"),
    )
    data_use_pyarrow: bool = Field(
        default=True,
        validation_alias=AliasChoices("DATA_USE_PYARROW", "data_use_pyarrow"),
    )

    # --- Databricks MCP client ---
    databricks_mcp_server_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATABRICKS_MCP_SERVER_URL", "databricks_mcp_server_url"
        ),
    )
    databricks_metrics_catalog: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATABRICKS_METRICS_CATALOG", "databricks_metrics_catalog"
        ),
    )
    databricks_metrics_schema: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATABRICKS_METRICS_SCHEMA", "databricks_metrics_schema"
        ),
    )
    databricks_metrics_table: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATABRICKS_METRICS_TABLE", "databricks_metrics_table"
        ),
    )
    databricks_metrics_sql: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATABRICKS_METRICS_SQL", "databricks_metrics_sql"
        ),
    )
    databricks_mcp_tool_name: str = Field(
        default="execute_sql",
        validation_alias=AliasChoices(
            "DATABRICKS_MCP_TOOL_NAME", "databricks_mcp_tool_name"
        ),
    )
    databricks_mcp_auth_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATABRICKS_MCP_AUTH_TOKEN", "databricks_mcp_auth_token"
        ),
    )
    databricks_mcp_timeout_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices(
            "DATABRICKS_MCP_TIMEOUT_SECONDS", "databricks_mcp_timeout_seconds"
        ),
    )

    # --- Daily report + Slack ---
    daily_report_top_n: int = Field(
        default=10,
        validation_alias=AliasChoices("DAILY_REPORT_TOP_N", "daily_report_top_n"),
    )
    daily_report_default_send_slack: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DAILY_REPORT_DEFAULT_SEND_SLACK", "daily_report_default_send_slack"
        ),
    )
    daily_report_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("DAILY_REPORT_ENABLED", "daily_report_enabled"),
    )
    daily_report_schedule_cron: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DAILY_REPORT_SCHEDULE_CRON", "daily_report_schedule_cron"
        ),
    )
    daily_report_hour: int = Field(
        default=8,
        validation_alias=AliasChoices("DAILY_REPORT_HOUR", "daily_report_hour"),
    )
    daily_report_minute: int = Field(
        default=0,
        validation_alias=AliasChoices("DAILY_REPORT_MINUTE", "daily_report_minute"),
    )
    daily_report_timezone: str = Field(
        default="UTC",
        validation_alias=AliasChoices("DAILY_REPORT_TIMEZONE", "daily_report_timezone"),
    )

    slack_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("SLACK_ENABLED", "slack_enabled"),
    )
    slack_webhook_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SLACK_WEBHOOK_URL", "slack_webhook_url"),
    )
    slack_timeout_seconds: float = Field(
        default=10.0,
        validation_alias=AliasChoices("SLACK_TIMEOUT_SECONDS", "slack_timeout_seconds"),
    )

    @field_validator(
        "retail_metrics_csv",
        "log_config_file",
        "data_schema_map_file",
        "retail_grain_min_avg",
        "retail_top_n",
        "data_read_chunk_size",
        "databricks_mcp_server_url",
        "databricks_metrics_catalog",
        "databricks_metrics_schema",
        "databricks_metrics_table",
        "databricks_metrics_sql",
        "databricks_mcp_auth_token",
        "slack_webhook_url",
        "daily_report_schedule_cron",
        "google_api_key",
        "openai_api_key",
        "anthropic_api_key",
        "litellm_api_base",
        "litellm_api_key",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return v

    def validate_llm_credentials(self) -> None:
        """Raise ValueError if the selected provider lacks required credentials."""
        if self.llm_provider == "googlegenai":
            if not self.google_api_key:
                raise ValueError(
                    "LLM_PROVIDER=googlegenai requires GOOGLE_API_KEY (or ADC for Vertex)."
                )
        elif self.llm_provider == "openai":
            if not self.openai_api_key:
                raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY.")
        elif self.llm_provider == "anthropic":
            if not self.anthropic_api_key:
                raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY.")
        elif self.llm_provider == "litellm":
            if not self.litellm_api_key and not self.litellm_api_base:
                raise ValueError(
                    "LLM_PROVIDER=litellm requires LITELLM_API_KEY and/or LITELLM_API_BASE."
                )

    def slack_configured(self) -> bool:
        return bool(self.slack_webhook_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
