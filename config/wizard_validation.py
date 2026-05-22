"""Validation helpers for the setup wizard."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def detect_local_timezone() -> str:
    """Best-effort IANA timezone from the system."""
    try:
        local = datetime.now().astimezone().tzinfo
        if local is not None:
            key = getattr(local, "key", None)
            if isinstance(key, str) and key:
                return key
    except Exception:
        pass
    return "UTC"


def validate_timezone(name: str) -> bool:
    """True if *name* is a valid IANA zone or a known friendly alias."""
    from config.timezone_aliases import normalize_timezone

    return normalize_timezone(name) is not None


def resolve_timezone(name: str) -> str | None:
    """Return canonical IANA timezone for storage, or ``None`` if invalid."""
    from config.timezone_aliases import normalize_timezone

    return normalize_timezone(name)


def validate_webhook_url(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if "hooks.slack.com" not in (parsed.netloc or ""):
        return False
    return bool(parsed.path and parsed.path != "/")


def validate_csv_path(path: Path) -> bool:
    return path.is_file()


def looks_like_placeholder_secret(value: str) -> bool:
    lower = value.strip().lower()
    placeholders = {"your-api-key", "changeme", "xxx", "sk-...", "placeholder"}
    return lower in placeholders or lower.startswith("your-")
