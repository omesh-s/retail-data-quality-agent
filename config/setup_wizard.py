"""Interactive terminal setup for .env configuration."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from config.env_file import mask_secret, merge_env_file, parse_env_file
from config.wizard_defaults import (
    PIPELINE_ADVANCED_DEFAULTS,
    PIPELINE_ADVANCED_OPTIONAL_KEYS,
    SAMPLE_CSV_RELATIVE,
)
from config.wizard_llm import (
    LITELLM_FAMILY_CHOICES,
    LITELLM_FAMILY_PRESETS,
    PROVIDER_CHOICES,
    PROVIDER_MODEL_PRESETS,
    is_suspicious_model_name,
    pick_model_from_presets,
)
from config.timezone_aliases import timezone_examples_hint
from config.wizard_validation import (
    detect_local_timezone,
    looks_like_placeholder_secret,
    resolve_timezone,
    validate_csv_path,
    validate_webhook_url,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass
class WizardSummary:
    llm_provider_label: str
    llm_model: str
    data_source_label: str
    slack_enabled: bool
    scheduler_enabled: bool
    advanced_customized: bool
    env_path: Path


def _prompt(text: str, default: str = "") -> str:
    try:
        import questionary
    except ImportError:
        suffix = f" [{default}]" if default else ""
        val = input(f"{text}{suffix}: ").strip()
        return val or default

    import questionary

    result = questionary.text(text, default=default or "").ask()
    return (result or default or "").strip()


def _confirm(text: str, default: bool = True) -> bool:
    try:
        import questionary
    except ImportError:
        val = input(f"{text} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        if not val:
            return default
        return val in ("y", "yes", "1", "true")

    import questionary

    return bool(questionary.confirm(text, default=default).ask())


def _select(text: str, choices: list[str]) -> str:
    try:
        import questionary
    except ImportError:
        print(f"\n{text}")
        for i, c in enumerate(choices, 1):
            print(f"  {i}. {c}")
        idx = int(input("Choice number: ").strip()) - 1
        return choices[idx]

    import questionary

    picked = questionary.select(text, choices=choices).ask()
    return picked or choices[0]


def _print_note(msg: str) -> None:
    print(f"  → {msg}")


def _configure_llm(existing: dict[str, str]) -> tuple[dict[str, str], str, str]:
    """Return env updates, display provider label, and model string."""
    updates: dict[str, str] = {}
    print("\n── LLM for summaries ──")
    _print_note(
        "ADK web chat stays on Google GenAI / Gemini. Other providers mainly affect "
        "run_day.py when LLM_PROVIDER is not googlegenai."
    )

    provider_labels = [label for label, _ in PROVIDER_CHOICES]
    provider_label = _select("How should run_day.py generate summaries?", provider_labels)
    provider_key = dict(PROVIDER_CHOICES)[provider_label]
    updates["LLM_PROVIDER"] = provider_key

    select_fn = _select
    prompt_fn = _prompt

    if provider_key == "litellm":
        _print_note(
            "LiteLLM routes requests to another provider; pick the family and a real model id."
        )
        family_labels = [label for label, _ in LITELLM_FAMILY_CHOICES]
        family_label = _select("Which provider will LiteLLM route to?", family_labels)
        family_key = dict(LITELLM_FAMILY_CHOICES)[family_label]
        presets = LITELLM_FAMILY_PRESETS[family_key]
        model = pick_model_from_presets(
            presets,
            select_fn=select_fn,
            prompt_fn=prompt_fn,
            title="LiteLLM model (routed id)",
            custom_hint="Full LiteLLM model string (e.g. anthropic/claude-3-5-sonnet-20241022)",
        )
        base = _prompt(
            "LITELLM_API_BASE (optional — leave blank if not needed)",
            existing.get("LITELLM_API_BASE", ""),
        )
        key = _prompt(
            "LITELLM_API_KEY (optional — leave blank if not needed)",
            existing.get("LITELLM_API_KEY", ""),
        )
        if base:
            updates["LITELLM_API_BASE"] = base
        if key and not looks_like_placeholder_secret(key):
            updates["LITELLM_API_KEY"] = key
    else:
        presets = PROVIDER_MODEL_PRESETS[provider_key]
        model = pick_model_from_presets(
            presets,
            select_fn=select_fn,
            prompt_fn=prompt_fn,
            title="Model",
            custom_hint="Custom model identifier",
        )
        _collect_direct_api_key(provider_key, existing, updates)

    updates["LLM_MODEL"] = model
    return updates, provider_label, model


def _collect_direct_api_key(
    provider_key: str, existing: dict[str, str], updates: dict[str, str]
) -> None:
    key_map = {
        "googlegenai": ("GOOGLE_API_KEY", "Google API key"),
        "openai": ("OPENAI_API_KEY", "OpenAI API key"),
        "anthropic": ("ANTHROPIC_API_KEY", "Anthropic API key"),
    }
    env_name, label = key_map[provider_key]
    while True:
        key = _prompt(label, existing.get(env_name, ""))
        if key and not looks_like_placeholder_secret(key):
            updates[env_name] = key
            return
        if _confirm(f"No {env_name} set. Continue anyway? (summaries will fail until set)", default=False):
            return
        print("  Please enter a key or confirm skip.")


def _configure_data_source(existing: dict[str, str]) -> tuple[dict[str, str], str]:
    print("\n── Metrics data source ──")
    ds_label = _select("Where do daily metrics come from?", ["Local CSV file", "Databricks MCP"])
    updates: dict[str, str] = {}
    if ds_label == "Local CSV file":
        updates["RETAIL_DATA_SOURCE"] = "local_csv"
        sample = PROJECT_ROOT / SAMPLE_CSV_RELATIVE
        default_csv = (
            existing.get("RETAIL_METRICS_CSV")
            or (SAMPLE_CSV_RELATIVE if sample.is_file() else "")
        )
        while True:
            csv_path = _prompt("Path to metrics CSV", default_csv)
            full = PROJECT_ROOT / csv_path
            if validate_csv_path(full):
                updates["RETAIL_METRICS_CSV"] = csv_path
                break
            print(f"  File not found: {full}")
            if not _confirm("Use this path anyway?", default=False):
                continue
            updates["RETAIL_METRICS_CSV"] = csv_path
            break
    else:
        updates["RETAIL_DATA_SOURCE"] = "databricks_mcp"
        updates["DATABRICKS_MCP_SERVER_URL"] = _prompt(
            "DATABRICKS_MCP_SERVER_URL (HTTP JSON-RPC endpoint)",
            existing.get("DATABRICKS_MCP_SERVER_URL", ""),
        )
        token = _prompt(
            "DATABRICKS_MCP_AUTH_TOKEN (optional)",
            existing.get("DATABRICKS_MCP_AUTH_TOKEN", ""),
        )
        if token:
            updates["DATABRICKS_MCP_AUTH_TOKEN"] = token
        if _confirm("Use full SQL override instead of catalog/schema/table?", default=False):
            updates["DATABRICKS_METRICS_SQL"] = _prompt(
                "DATABRICKS_METRICS_SQL",
                existing.get(
                    "DATABRICKS_METRICS_SQL",
                    "SELECT * FROM catalog.schema.table",
                ),
            )
        else:
            updates["DATABRICKS_METRICS_CATALOG"] = _prompt(
                "DATABRICKS_METRICS_CATALOG",
                existing.get("DATABRICKS_METRICS_CATALOG", "retail"),
            )
            updates["DATABRICKS_METRICS_SCHEMA"] = _prompt(
                "DATABRICKS_METRICS_SCHEMA",
                existing.get("DATABRICKS_METRICS_SCHEMA", "metrics"),
            )
            updates["DATABRICKS_METRICS_TABLE"] = _prompt(
                "DATABRICKS_METRICS_TABLE",
                existing.get("DATABRICKS_METRICS_TABLE", "daily_store_metrics"),
            )
    return updates, ds_label


def _configure_slack(existing: dict[str, str]) -> tuple[dict[str, str], bool]:
    print("\n── Slack (daily report webhook) ──")
    _print_note("Incoming webhook only — not an interactive Slack bot.")
    enabled = _confirm("Enable daily Slack notifications?", default=False)
    updates: dict[str, str] = {
        "SLACK_ENABLED": "true" if enabled else "false",
        "DAILY_REPORT_DEFAULT_SEND_SLACK": "true" if enabled else "false",
    }
    if not enabled:
        return updates, False

    while True:
        webhook = _prompt(
            "SLACK_WEBHOOK_URL",
            existing.get("SLACK_WEBHOOK_URL", ""),
        )
        if validate_webhook_url(webhook):
            updates["SLACK_WEBHOOK_URL"] = webhook
            if _confirm("Send a test message now?", default=False):
                _send_test_slack(webhook)
            return updates, True
        print("  URL should be https://hooks.slack.com/services/…")
        if _confirm("Disable Slack for now?", default=True):
            updates["SLACK_ENABLED"] = "false"
            updates["DAILY_REPORT_DEFAULT_SEND_SLACK"] = "false"
            return updates, False


def _configure_scheduler(existing: dict[str, str]) -> tuple[dict[str, str], bool]:
    print("\n── Local daily scheduler (optional) ──")
    _print_note(
        "schedule_daily_report.py --loop is for local/dev. Production: cron, Cloud Scheduler, "
        "or POST /internal/daily-report."
    )
    enabled = _confirm("Enable local daily scheduler?", default=False)
    if not enabled:
        return {"DAILY_REPORT_ENABLED": "false"}, False

    detected_tz = detect_local_timezone()
    if detected_tz == "UTC":
        _print_note(
            "Could not detect local timezone. Enter an IANA zone like America/Chicago, "
            "or a friendly alias like CST, Central, or Chicago."
        )

    updates: dict[str, str] = {"DAILY_REPORT_ENABLED": "true"}
    updates["DAILY_REPORT_HOUR"] = _prompt(
        "Hour (0-23)", existing.get("DAILY_REPORT_HOUR", "8")
    )
    updates["DAILY_REPORT_MINUTE"] = _prompt(
        "Minute (0-59)", existing.get("DAILY_REPORT_MINUTE", "0")
    )
    tz_prompt = (
        "Timezone (IANA or friendly alias, e.g. America/Chicago, CST, Central, Chicago, UTC)"
    )
    while True:
        raw_tz = _prompt(
            tz_prompt,
            existing.get("DAILY_REPORT_TIMEZONE", detected_tz),
        )
        canonical = resolve_timezone(raw_tz)
        if canonical:
            if canonical != raw_tz.strip():
                print(f"  Using {canonical} for '{raw_tz.strip()}'.")
            updates["DAILY_REPORT_TIMEZONE"] = canonical
            break
        print(f"  Invalid timezone. {timezone_examples_hint()}")
    return updates, True


def _configure_advanced(existing: dict[str, str]) -> tuple[dict[str, str], bool]:
    print("\n── Advanced pipeline settings (optional) ──")
    _print_note("You can change these later in .env without re-running the wizard.")
    if not _confirm("Configure advanced anomaly pipeline settings now?", default=False):
        updates = dict(PIPELINE_ADVANCED_DEFAULTS)
        return updates, False

    updates: dict[str, str] = {}
    updates["RETAIL_HISTORY_DAYS"] = _prompt(
        "RETAIL_HISTORY_DAYS", existing.get("RETAIL_HISTORY_DAYS", "30")
    )
    updates["RETAIL_Z_THRESHOLD"] = _prompt(
        "RETAIL_Z_THRESHOLD", existing.get("RETAIL_Z_THRESHOLD", "4.0")
    )
    updates["RETAIL_GRAIN_MIN_DISTINCT"] = _prompt(
        "RETAIL_GRAIN_MIN_DISTINCT", existing.get("RETAIL_GRAIN_MIN_DISTINCT", "3")
    )
    grain_avg = _prompt(
        "RETAIL_GRAIN_MIN_AVG (blank = unset)",
        existing.get("RETAIL_GRAIN_MIN_AVG", ""),
    )
    if grain_avg:
        updates["RETAIL_GRAIN_MIN_AVG"] = grain_avg
    top_n = _prompt("RETAIL_TOP_N (blank = unset)", existing.get("RETAIL_TOP_N", ""))
    if top_n:
        updates["RETAIL_TOP_N"] = top_n
    updates["DAILY_REPORT_TOP_N"] = _prompt(
        "DAILY_REPORT_TOP_N", existing.get("DAILY_REPORT_TOP_N", "10")
    )
    return updates, True


def _print_confirmation(summary: WizardSummary, updates: dict[str, str]) -> None:
    print("\n" + "=" * 60)
    print("Setup complete")
    print("=" * 60)
    print(f"  Config file:     {summary.env_path}")
    print(f"  LLM:             {summary.llm_provider_label}")
    print(f"  Model:           {summary.llm_model}")
    print(f"  Data source:     {summary.data_source_label}")
    print(f"  Slack:           {'enabled' if summary.slack_enabled else 'disabled'}")
    print(f"  Scheduler:       {'enabled' if summary.scheduler_enabled else 'disabled'}")
    print(
        f"  Pipeline tuning: "
        f"{'customized' if summary.advanced_customized else 'defaults (30d history, z=4.0, grain distinct=3)'}"
    )
    print("\n  Environment keys written:")
    for key in sorted(updates):
        val = updates[key] or ""
        if any(s in key for s in ("KEY", "TOKEN", "WEBHOOK")):
            print(f"    {key}={mask_secret(val)}")
        else:
            print(f"    {key}={val}")
    print("\n  Next commands:")
    print("    python evaluate.py")
    print("    python run_day.py --date 2024-05-20")
    print("    python run_daily_report.py --date 2024-05-20 --send-slack")
    print("    python schedule_daily_report.py --once")
    print("    adk web .")
    print("=" * 60)


def run_wizard(env_path: Path = DEFAULT_ENV_PATH, *, interactive: bool = True) -> int:
    if not interactive:
        print("Non-interactive wizard: use interactive mode (default).", file=sys.stderr)
        return 1

    print("Retail Data Quality Agent — setup wizard")
    print("Basic setup: LLM, data source, Slack, scheduler. Advanced pipeline settings are optional.\n")

    existing = parse_env_file(env_path)
    updates: dict[str, str | None] = {}

    llm_updates, provider_label, model = _configure_llm(existing)
    updates.update(llm_updates)

    ds_updates, ds_label = _configure_data_source(existing)
    updates.update(ds_updates)

    slack_updates, slack_on = _configure_slack(existing)
    updates.update(slack_updates)

    sched_updates, sched_on = _configure_scheduler(existing)
    updates.update(sched_updates)

    adv_updates, adv_custom = _configure_advanced(existing)
    updates.update(adv_updates)

    merge_env_file(env_path, updates)

    summary = WizardSummary(
        llm_provider_label=provider_label,
        llm_model=model,
        data_source_label=ds_label,
        slack_enabled=slack_on,
        scheduler_enabled=sched_on,
        advanced_customized=adv_custom,
        env_path=env_path,
    )
    _print_confirmation(summary, {k: v for k, v in updates.items() if v is not None})
    return 0


def _send_test_slack(webhook: str) -> None:
    if not webhook:
        print("  No webhook URL; skipping test.")
        return
    from config.settings import Settings
    from myagent.integrations.slack import send_slack_webhook

    s = Settings(slack_webhook_url=webhook, slack_timeout_seconds=10.0)
    result = send_slack_webhook("Retail DQ setup wizard — test message.", s)
    if result.ok:
        print("  Test Slack message sent.")
    else:
        print(f"  Test Slack failed: {result.error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive .env setup wizard")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help="Path to .env file (default: project .env)",
    )
    args = parser.parse_args(argv)
    return run_wizard(args.env_file)


if __name__ == "__main__":
    raise SystemExit(main())
