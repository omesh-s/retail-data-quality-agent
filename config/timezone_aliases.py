"""Map friendly timezone shorthand to canonical IANA identifiers."""

from __future__ import annotations

# Normalized lookup key -> canonical IANA timezone (region-based for US zones).
TIMEZONE_ALIAS_MAP: dict[str, str] = {}

_RAW_ALIASES: dict[str, str] = {
    # Central
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "ct": "America/Chicago",
    "central": "America/Chicago",
    "centraltime": "America/Chicago",
    "chicago": "America/Chicago",
    "uscentral": "America/Chicago",
    # Eastern
    "est": "America/New_York",
    "edt": "America/New_York",
    "et": "America/New_York",
    "eastern": "America/New_York",
    "easterntime": "America/New_York",
    "newyork": "America/New_York",
    "ny": "America/New_York",
    "useastern": "America/New_York",
    # Mountain
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "mt": "America/Denver",
    "mountain": "America/Denver",
    "mountaintime": "America/Denver",
    "denver": "America/Denver",
    "usmountain": "America/Denver",
    # Pacific
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "pt": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
    "pacifictime": "America/Los_Angeles",
    "losangeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "uspacific": "America/Los_Angeles",
    # UTC / GMT
    "utc": "UTC",
    "gmt": "UTC",
    "z": "UTC",
}


def _normalize_lookup_key(value: str) -> str:
    """Lowercase alphanumeric key for alias lookup."""
    return "".join(c for c in value.strip().lower() if c.isalnum())


def _build_alias_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for alias, iana in _RAW_ALIASES.items():
        out[_normalize_lookup_key(alias)] = iana
    # Also allow IANA paths without caring about case on region/city parts
    return out


TIMEZONE_ALIAS_MAP.update(_build_alias_map())


def _is_valid_iana(name: str) -> bool:
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(name)
        return True
    except Exception:
        return False


def _resolve_iana_case_insensitive(raw: str) -> str | None:
    if _is_valid_iana(raw):
        return raw
    lowered = raw.strip().lower()
    try:
        from zoneinfo import available_timezones

        for tz in available_timezones():
            if tz.lower() == lowered:
                return tz
    except Exception:
        pass
    return None


def normalize_timezone(value: str) -> str | None:
    """Resolve *value* to a canonical IANA timezone, or ``None`` if invalid.

    Accepts valid IANA names (any casing on the path) and known friendly aliases
    (CST, Central, Chicago, etc.). Stored config should always use the return value.
    """
    raw = (value or "").strip()
    if not raw:
        return None

    # Friendly aliases before IANA lookup (EST/GMT are valid legacy IANA ids we remap).
    key = _normalize_lookup_key(raw)
    if key in TIMEZONE_ALIAS_MAP:
        return TIMEZONE_ALIAS_MAP[key]

    iana = _resolve_iana_case_insensitive(raw)
    if iana:
        return iana

    return None


def timezone_examples_hint() -> str:
    return (
        "Examples: America/Chicago, CST, Central, Chicago, "
        "America/New_York, EST, UTC"
    )
