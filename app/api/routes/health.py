"""Health check route."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.responses import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Liveness probe for orchestrators and local sanity checks."""
    logger.debug("health check")
    return HealthResponse()
