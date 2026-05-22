"""Generate anomaly summaries via configured LLM provider (non-ADK CLI path)."""

from __future__ import annotations

import logging
import os

from config.settings import Settings

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a retail data quality analyst. Summarize the structured anomaly input. "
    "Use severities and issue types exactly as provided; do not invent anomalies."
)


def generate_text_summary(settings: Settings, user_prompt: str) -> str:
    """Call the configured provider and return model text."""
    settings.validate_llm_credentials()
    provider = settings.llm_provider
    model = settings.llm_model

    if provider == "openai":
        return _openai_chat(settings, user_prompt, model)
    if provider == "anthropic":
        return _anthropic_chat(settings, user_prompt, model)
    if provider == "litellm":
        return _litellm_chat(settings, user_prompt, model)
    raise ValueError(
        f"Provider {provider!r} is not supported by generate_text_summary. "
        "Use googlegenai with run_day.py (ADK) or set LLM_PROVIDER to openai, anthropic, or litellm."
    )


def _openai_chat(settings: Settings, prompt: str, model: str) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("openai package required for LLM_PROVIDER=openai") from exc

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _anthropic_chat(settings: Settings, prompt: str, model: str) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError("anthropic package required for LLM_PROVIDER=anthropic") from exc

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [b.text for b in resp.content if hasattr(b, "text")]
    return "\n".join(parts).strip()


def _litellm_chat(settings: Settings, prompt: str, model: str) -> str:
    import litellm

    if settings.litellm_api_key:
        os.environ.setdefault("LITELLM_API_KEY", settings.litellm_api_key)
    if settings.litellm_api_base:
        os.environ.setdefault("LITELLM_API_BASE", settings.litellm_api_base)

    resp = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    return (resp.choices[0].message.content or "").strip()
