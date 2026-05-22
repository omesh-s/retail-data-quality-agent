"""Timezone alias normalization for setup wizard."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from config.env_file import merge_env_file, parse_env_file
from config.timezone_aliases import normalize_timezone
from config.wizard_validation import resolve_timezone, validate_timezone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("America/Chicago", "America/Chicago"),
        ("UTC", "UTC"),
        ("CST", "America/Chicago"),
        ("CT", "America/Chicago"),
        ("Chicago", "America/Chicago"),
        ("central", "America/Chicago"),
        ("Central Time", "America/Chicago"),
        ("EST", "America/New_York"),
        ("Eastern", "America/New_York"),
        ("PST", "America/Los_Angeles"),
        ("LA", "America/Los_Angeles"),
        ("GMT", "UTC"),
        ("cst", "America/Chicago"),
        ("america/chicago", "America/Chicago"),
    ],
)
def test_normalize_timezone_aliases(raw: str, expected: str) -> None:
    assert normalize_timezone(raw) == expected


@pytest.mark.parametrize("raw", ["", "NotAZone", "foobar", "CSTX", "Midwest"])
def test_normalize_timezone_rejects_invalid(raw: str) -> None:
    assert normalize_timezone(raw) is None
    assert validate_timezone(raw) is False


def test_resolve_timezone_wrapper():
    assert resolve_timezone("CST") == "America/Chicago"


def test_wizard_stores_canonical_iana_for_cst_alias(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    canonical = resolve_timezone("CST")
    assert canonical == "America/Chicago"
    merge_env_file(env, {"DAILY_REPORT_TIMEZONE": canonical})
    assert parse_env_file(env)["DAILY_REPORT_TIMEZONE"] == "America/Chicago"


@patch("config.setup_wizard._prompt", side_effect=["8", "0", "CST"])
@patch("config.setup_wizard._confirm", return_value=True)
def test_configure_scheduler_normalizes_cst(_confirm, _prompt, tmp_path: Path) -> None:
    from config.setup_wizard import _configure_scheduler

    updates, enabled = _configure_scheduler({})
    assert enabled is True
    assert updates["DAILY_REPORT_TIMEZONE"] == "America/Chicago"
