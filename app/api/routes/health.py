# Health check route.

from __future__ import annotations

import logging

from fastapi import APIRouter, Response

from app.schemas.responses import HealthResponse, ReadinessCheck, ReadinessResponse
from config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


# Liveness probe for orchestrators and local sanity checks.
@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    logger.debug("health check")
    return HealthResponse()


@router.get("/ready", response_model=ReadinessResponse, tags=["health"])
def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe for config and MCP script availability."""
    s = get_settings()
    checks: list[ReadinessCheck] = []

    try:
        s.validate_llm_credentials()
        checks.append(
            ReadinessCheck(
                name="llm_credentials",
                status="ok",
                detail=f"Provider {s.llm_provider} configured.",
            )
        )
    except ValueError as exc:
        checks.append(ReadinessCheck(name="llm_credentials", status="fail", detail=str(exc)))

    try:
        s.validate_mcp_runtime()
        if s.wfm_dq_mcp_transport_for_adk == "sse":
            checks.append(
                ReadinessCheck(
                    name="mcp_transport",
                    status="ok",
                    detail=(
                        "SSE transport configured"
                        f" (url={s.wfm_dq_mcp_server_url_for_adk}, "
                        f"auth_required={s.wfm_dq_mcp_require_auth_for_sse})."
                    ),
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    name="mcp_transport",
                    status="ok",
                    detail=(
                        "Stdio transport configured with script "
                        f"{s.wfm_dq_mcp_server_path_for_adk}."
                    ),
                )
            )
    except ValueError as exc:
        checks.append(ReadinessCheck(name="mcp_transport", status="fail", detail=str(exc)))

    ready = all(c.status == "ok" for c in checks)
    if not ready:
        response.status_code = 503
    return ReadinessResponse(status="ready" if ready else "not_ready", checks=checks)
