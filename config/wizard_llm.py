"""LLM preset catalogs and validation for the setup wizard."""

from __future__ import annotations

from typing import Callable

# Top-level wizard labels -> settings LLM_PROVIDER value
PROVIDER_CHOICES: list[tuple[str, str]] = [
    ("Google GenAI / Gemini", "googlegenai"),
    ("OpenAI", "openai"),
    ("Anthropic / Claude", "anthropic"),
    ("LiteLLM (proxy to another provider)", "litellm"),
]

# Curated models per direct provider (label, model id). First entry = recommended default.
PROVIDER_MODEL_PRESETS: dict[str, list[tuple[str, str]]] = {
    "googlegenai": [
        ("gemini-2.5-flash (recommended)", "gemini-2.5-flash"),
        ("gemini-2.0-flash", "gemini-2.0-flash"),
        ("gemini-2.5-pro", "gemini-2.5-pro"),
        ("Custom model…", "__custom__"),
    ],
    "openai": [
        ("gpt-4o-mini (recommended)", "gpt-4o-mini"),
        ("gpt-4.1-mini", "gpt-4.1-mini"),
        ("gpt-4.1", "gpt-4.1"),
        ("gpt-4o", "gpt-4o"),
        ("Custom model…", "__custom__"),
    ],
    "anthropic": [
        ("claude-3-5-sonnet (recommended)", "claude-3-5-sonnet-20241022"),
        ("claude-3-5-haiku", "claude-3-5-haiku-20241022"),
        ("claude-3-7-sonnet", "claude-3-7-sonnet-20250219"),
        ("Custom model…", "__custom__"),
    ],
}

LITELLM_FAMILY_CHOICES: list[tuple[str, str]] = [
    ("Gemini", "gemini"),
    ("OpenAI / GPT", "openai"),
    ("Anthropic / Claude", "anthropic"),
    ("Other / custom", "other"),
]

LITELLM_FAMILY_PRESETS: dict[str, list[tuple[str, str]]] = {
    "gemini": [
        ("gemini-2.5-flash (recommended)", "gemini/gemini-2.5-flash"),
        ("gemini-2.0-flash", "gemini/gemini-2.0-flash"),
        ("gemini-2.5-pro", "gemini/gemini-2.5-pro"),
        ("Custom model…", "__custom__"),
    ],
    "openai": [
        ("gpt-4o-mini (recommended)", "gpt-4o-mini"),
        ("gpt-4.1-mini", "gpt-4.1-mini"),
        ("gpt-4.1", "gpt-4.1"),
        ("gpt-4o", "gpt-4o"),
        ("Custom model…", "__custom__"),
    ],
    "anthropic": [
        ("claude-3-5-sonnet (recommended)", "anthropic/claude-3-5-sonnet-20241022"),
        ("claude-3-5-haiku", "anthropic/claude-3-5-haiku-20241022"),
        ("claude-3-7-sonnet", "anthropic/claude-3-7-sonnet-20250219"),
        ("Custom model…", "__custom__"),
    ],
    "other": [
        ("Custom model…", "__custom__"),
    ],
}

# Normalized tokens that look like a provider name, not a routable model id.
_PROVIDER_ONLY_LABELS = frozenset(
    {
        "anthropic",
        "openai",
        "google",
        "gemini",
        "googlegenai",
        "claude",
        "gpt",
        "litellm",
        "chatgpt",
        "vertex",
        "bedrock",
    }
)

CUSTOM_SENTINEL = "__custom__"


def normalize_model_token(model: str) -> str:
    return "".join(c for c in model.strip().lower() if c.isalnum())


def is_suspicious_model_name(model: str) -> bool:
    """True when *model* looks like a provider label only (e.g. ``anthropic``)."""
    token = normalize_model_token(model)
    if not token:
        return True
    return token in _PROVIDER_ONLY_LABELS


def resolve_preset_model(
    presets: list[tuple[str, str]],
    choice_label: str,
    *,
    custom_value: str = "",
) -> str:
    """Map a preset menu label to the stored model string."""
    for label, model_id in presets:
        if label == choice_label:
            if model_id == CUSTOM_SENTINEL:
                return custom_value.strip()
            return model_id
    return custom_value.strip() or presets[0][1]


def pick_model_from_presets(
    presets: list[tuple[str, str]],
    *,
    select_fn: Callable[[str, list[str]], str],
    prompt_fn: Callable[[str, str], str],
    title: str,
    custom_hint: str = "Enter the full model identifier",
) -> str:
    """Interactive model pick: curated list or custom string with validation."""
    labels = [label for label, _ in presets]
    while True:
        choice = select_fn(title, labels)
        if any(mid == CUSTOM_SENTINEL and label == choice for label, mid in presets):
            custom = prompt_fn(custom_hint, "").strip()
            if is_suspicious_model_name(custom):
                print(
                    "  That looks like a provider name, not a model id "
                    "(e.g. use claude-3-5-sonnet or gemini-2.5-flash)."
                )
                continue
            if not custom:
                print("  Model id cannot be empty.")
                continue
            return custom
        model = resolve_preset_model(presets, choice)
        if is_suspicious_model_name(model):
            print(f"  '{model}' does not look like a valid model id; choose again.")
            continue
        return model
