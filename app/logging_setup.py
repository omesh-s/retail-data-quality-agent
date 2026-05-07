"""Application logging: console, optional JSON, or YAML dictConfig."""

from __future__ import annotations

import json
import logging
import logging.config
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from config.settings import get_settings


class JsonLogFormatter(logging.Formatter):
    """Minimal JSON lines for machine-readable logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Idempotent setup from settings: YAML file wins, else console vs json."""
    settings = get_settings()
    if settings.log_config_file and settings.log_config_file.is_file():
        with settings.log_config_file.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        logging.config.dictConfig(cfg)
        return

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    if settings.log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
