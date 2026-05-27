# FastAPI entrypoint: health and future operational endpoints.
# Run: uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
# Complements adk web (chat); small HTTP surface for probes and automation.

from __future__ import annotations

import logging
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import daily_report as daily_report_routes
from app.api.routes import health as health_routes
from app.logging_setup import configure_logging
from app.request_context import reset_request_id, set_request_id
from app.schemas.responses import ErrorResponse
from config.settings import get_settings

# Load .env then stdout/file logging per settings.
load_dotenv()
configure_logging()

logger = logging.getLogger(__name__)

# FastAPI app instance (routers mounted below).
app = FastAPI(
    title="Retail Data Quality API",
    description="Companion HTTP service for the retail anomaly detection pipeline.",
    version="0.1.0",
)


# Return 422 with ErrorResponse JSON when request body/query fails validation.
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="validation_error",
            detail=str(exc),
        ).model_dump(),
    )


app.include_router(health_routes.router)
app.include_router(daily_report_routes.router)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers["x-request-id"] = request_id
    return response


# One-time log line when the process starts.
@app.on_event("startup")
async def startup() -> None:
    s = get_settings()
    logger.info(
        "Retail Data Quality API starting host=%s port=%s log_format=%s mcp_transport=%s",
        s.service_host,
        s.service_port,
        s.log_format,
        s.wfm_dq_mcp_transport_for_adk,
    )


# Dev entry: run uvicorn with host/port from settings.
if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.service_host,
        port=s.service_port,
        reload=True,
    )
