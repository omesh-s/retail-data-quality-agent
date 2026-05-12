# Shared response schemas for the companion HTTP API.

from __future__ import annotations

from pydantic import BaseModel, Field


# GET /health JSON body.
class HealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Overall service status")
    service: str = Field(
        default="retail-data-quality-api",
        description="Logical service name",
    )


# Simple { "message": "..." } wrapper.
class MessageResponse(BaseModel):
    message: str = Field(..., description="Human-readable message")


# API error shape (e.g. validation_handler).
class ErrorResponse(BaseModel):
    error: str = Field(..., description="Short error code or label")
    detail: str | None = Field(default=None, description="Optional explanation")
