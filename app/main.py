"""FastAPI entrypoint: health and future operational endpoints.

Run from project root::

    uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

This does **not** replace ``adk web .``; the ADK chat UI remains the primary
browser experience for the Gemini agent. This app complements it with a small
HTTP surface for probes and future automation.
"""

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

load_dotenv()
configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Retail Data Quality API",
    description="Companion HTTP service for the retail anomaly detection pipeline.",
    version="0.1.0",
)


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


@app.on_event("startup")
async def startup() -> None:
    logger.info(
        "Retail Data Quality API starting (retail pipeline unchanged; ADK chat uses myagent/)."
    )


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.service_host,
        port=s.service_port,
        reload=True,
    )
