"""Shared response schemas for the companion HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """``GET /health`` payload."""

    status: str = Field(default="healthy", description="Overall service status")
    service: str = Field(
        default="retail-data-quality-api",
        description="Logical service name",
    )


class MessageResponse(BaseModel):
    """Generic single-message body."""

    message: str = Field(..., description="Human-readable message")


class ErrorResponse(BaseModel):
    """Structured error for API clients."""

    error: str = Field(..., description="Short error code or label")
    detail: str | None = Field(default=None, description="Optional explanation")
