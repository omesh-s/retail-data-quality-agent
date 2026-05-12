# FastAPI entrypoint: health and future operational endpoints.
# Run: uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
# Complements adk web (chat); small HTTP surface for probes and automation.

from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import health as health_routes
from app.logging_setup import configure_logging
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
async def validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="validation_error",
            detail=str(exc),
        ).model_dump(),
    )


app.include_router(health_routes.router)


# One-time log line when the process starts.
@app.on_event("startup")
async def startup() -> None:
    logger.info(
        "Retail Data Quality API starting (retail pipeline unchanged; ADK chat uses myagent/)."
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
