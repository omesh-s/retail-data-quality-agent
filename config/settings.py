# Central settings for MCP-first ADK runtime.

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProvider = Literal["googlegenai", "openai", "anthropic", "litellm"]
LogFormat = Literal["console", "json"]
McpTransport = Literal["stdio", "sse"]


class Settings(BaseSettings):
    """Single source of truth for MCP-first ADK runtime config."""

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

    # --- ADK MCP toolset ---
    wfm_dq_mcp_server_path_for_adk: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WFM_DQ_MCP_SERVER_PATH_FOR_ADK", "wfm_dq_mcp_server_path_for_adk"
        ),
    )
    wfm_dq_mcp_python_for_adk: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WFM_DQ_MCP_PYTHON_FOR_ADK", "wfm_dq_mcp_python_for_adk"),
    )
    wfm_dq_mcp_server_timeout_for_adk: float = Field(
        default=90.0,
        validation_alias=AliasChoices(
            "WFM_DQ_MCP_SERVER_TIMEOUT_FOR_ADK",
            "wfm_dq_mcp_server_timeout_for_adk",
        ),
    )
    wfm_dq_mcp_transport_for_adk: McpTransport = Field(
        default="stdio",
        validation_alias=AliasChoices(
            "WFM_DQ_MCP_TRANSPORT_FOR_ADK",
            "wfm_dq_mcp_transport_for_adk",
        ),
    )
    wfm_dq_mcp_server_url_for_adk: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WFM_DQ_MCP_SERVER_URL_FOR_ADK",
            "wfm_dq_mcp_server_url_for_adk",
        ),
    )
    wfm_dq_mcp_auth_token_for_adk: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK",
            "wfm_dq_mcp_auth_token_for_adk",
        ),
    )
    wfm_dq_mcp_require_auth_for_sse: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "WFM_DQ_MCP_REQUIRE_AUTH_FOR_SSE",
            "wfm_dq_mcp_require_auth_for_sse",
        ),
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

    # --- Companion HTTP service ---
    service_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("SERVICE_HOST", "service_host"),
    )
    service_port: int = Field(
        default=8080,
        validation_alias=AliasChoices("SERVICE_PORT", "service_port"),
    )

    @field_validator(
        "google_api_key",
        "openai_api_key",
        "anthropic_api_key",
        "litellm_api_base",
        "litellm_api_key",
        "wfm_dq_mcp_server_path_for_adk",
        "wfm_dq_mcp_python_for_adk",
        "wfm_dq_mcp_server_url_for_adk",
        "wfm_dq_mcp_auth_token_for_adk",
        "log_config_file",
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

    def validate_mcp_runtime(self) -> None:
        """Raise ValueError when MCP runtime settings are invalid."""
        if self.wfm_dq_mcp_transport_for_adk == "stdio":
            if not self.wfm_dq_mcp_server_path_for_adk:
                raise ValueError(
                    "WFM_DQ_MCP_SERVER_PATH_FOR_ADK must be set when "
                    "WFM_DQ_MCP_TRANSPORT_FOR_ADK=stdio."
                )
            script = Path(self.wfm_dq_mcp_server_path_for_adk).expanduser()
            if not script.is_file():
                raise ValueError(
                    f"WFM_DQ_MCP_SERVER_PATH_FOR_ADK does not point to an existing file: {script}"
                )
            return

        if not self.wfm_dq_mcp_server_url_for_adk:
            raise ValueError(
                "WFM_DQ_MCP_SERVER_URL_FOR_ADK must be set when WFM_DQ_MCP_TRANSPORT_FOR_ADK=sse."
            )
        if self.wfm_dq_mcp_require_auth_for_sse and not self.wfm_dq_mcp_auth_token_for_adk:
            raise ValueError(
                "WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK must be set when "
                "WFM_DQ_MCP_REQUIRE_AUTH_FOR_SSE=true."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
