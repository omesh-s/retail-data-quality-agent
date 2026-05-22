"""Setup wizard helpers and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.wizard_defaults import PIPELINE_ADVANCED_DEFAULTS, SAMPLE_CSV_RELATIVE
from config.wizard_llm import (
    LITELLM_FAMILY_PRESETS,
    PROVIDER_MODEL_PRESETS,
    is_suspicious_model_name,
    pick_model_from_presets,
    resolve_preset_model,
)
from config.wizard_validation import (
    validate_csv_path,
    validate_timezone,
    validate_webhook_url,
)
from config.env_file import merge_env_file, parse_env_file


def test_provider_only_model_names_are_suspicious():
    assert is_suspicious_model_name("anthropic")
    assert is_suspicious_model_name("openai")
    assert not is_suspicious_model_name("gemini-2.5-flash")
    assert not is_suspicious_model_name("anthropic/claude-3-5-sonnet-20241022")


def test_litellm_family_presets_have_real_models():
    for family, presets in LITELLM_FAMILY_PRESETS.items():
        if family == "other":
            continue
        models = [m for _, m in presets if m != "__custom__"]
        assert models
        assert not any(is_suspicious_model_name(m) for m in models)


def test_resolve_preset_model_custom():
    presets = PROVIDER_MODEL_PRESETS["openai"]
    assert resolve_preset_model(presets, "Custom model…", custom_value="gpt-4o") == "gpt-4o"


def test_pick_model_rejects_suspicious_custom():
    presets = PROVIDER_MODEL_PRESETS["anthropic"]
    calls = {"n": 0}

    def select_fn(_title: str, labels: list[str]) -> str:
        return labels[-1]

    def prompt_fn(_title: str, _default: str) -> str:
        calls["n"] += 1
        return "anthropic" if calls["n"] == 1 else "claude-3-5-haiku-20241022"

    model = pick_model_from_presets(
        presets, select_fn=select_fn, prompt_fn=prompt_fn, title="Model"
    )
    assert model.startswith("claude")
    assert calls["n"] >= 2


def test_advanced_defaults_when_skipped():
    assert PIPELINE_ADVANCED_DEFAULTS["RETAIL_HISTORY_DAYS"] == "30"
    assert PIPELINE_ADVANCED_DEFAULTS["RETAIL_Z_THRESHOLD"] == "4.0"
    assert "RETAIL_TOP_N" not in PIPELINE_ADVANCED_DEFAULTS


def test_validate_webhook_and_timezone():
    assert validate_webhook_url("https://hooks.slack.com/services/T/B/x")
    assert not validate_webhook_url("https://example.com/hook")
    assert validate_timezone("UTC")
    assert validate_timezone("CST")
    assert not validate_timezone("Not/A/Zone")


def test_validate_sample_csv_exists():
    root = Path(__file__).resolve().parent.parent
    assert validate_csv_path(root / SAMPLE_CSV_RELATIVE)


def test_merge_env_writes_llm_keys(tmp_path):
    env = tmp_path / ".env"
    merge_env_file(
        env,
        {
            "LLM_PROVIDER": "litellm",
            "LLM_MODEL": "anthropic/claude-3-5-sonnet-20241022",
            "RETAIL_DATA_SOURCE": "local_csv",
        },
    )
    parsed = parse_env_file(env)
    assert parsed["LLM_PROVIDER"] == "litellm"
    assert "claude" in parsed["LLM_MODEL"]
