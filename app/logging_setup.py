# Application logging: console, optional JSON, or YAML dictConfig.

from __future__ import annotations

import json
import logging
import logging.config
from datetime import datetime, timezone
from typing import Any

import yaml

from app.request_context import get_request_id
from config.settings import get_settings


# logging.Formatter that emits one JSON object per log line.
class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Serialize record as one JSON object per line.
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class RequestContextFilter(logging.Filter):
    """Inject request_id into log records for correlation."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


# Configure root logger from settings (dictConfig file if set, else stream + level).
def configure_logging() -> None:
    settings = get_settings()
    if settings.log_config_file and settings.log_config_file.is_file():
        with settings.log_config_file.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        logging.config.dictConfig(cfg)
        return

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    if settings.log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s [req=%(request_id)s]: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
