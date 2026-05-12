# Health check route.

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.responses import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# Liveness probe for orchestrators and local sanity checks.
@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    logger.debug("health check")
    return HealthResponse()
