"""Interactive terminal setup for .env configuration — ADK-first."""

from __future__ import annotations

import argparse
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

from config.env_file import mask_secret, merge_env_file, parse_env_file
from config.wizard_defaults import (
    PIPELINE_ADVANCED_DEFAULTS,
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

# ── Usage modes ──────────────────────────────────────────────────────────────

MODE_ADK_LOCAL = "adk_local"
MODE_ADK_MCP = "adk_mcp"
MODE_DEVELOPER = "developer"

MODE_CHOICES: list[tuple[str, str]] = [
    ("ADK web with local sample data (quickstart)", MODE_ADK_LOCAL),
    ("ADK web with external MCP server (Databricks)", MODE_ADK_MCP),
    ("Developer / advanced setup", MODE_DEVELOPER),
]


@dataclass
class WizardSummary:
    mode: str
    llm_provider_label: str
    llm_model: str
    data_source_label: str
    mcp_adk_enabled: bool = False
    slack_enabled: bool = False
    scheduler_enabled: bool = False
    advanced_customized: bool = False
    env_path: Path = DEFAULT_ENV_PATH
    extra_notes: list[str] = field(default_factory=list)


# ── UI helpers ───────────────────────────────────────────────────────────────


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


# ── LLM setup (shared by all modes) ─────────────────────────────────────────


def _configure_llm(existing: dict[str, str]) -> tuple[dict[str, str], str, str]:
    """Return env updates, display provider label, and model string."""
    updates: dict[str, str] = {}
    print("\n── Step 1: LLM ──")
    _print_note(
        "ADK web uses Google GenAI (Gemini) by default. "
        "Other providers affect CLI tools (run_day.py)."
    )

    provider_labels = [label for label, _ in PROVIDER_CHOICES]
    provider_label = _select("LLM provider", provider_labels)
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


# ── Mode selection ───────────────────────────────────────────────────────────


def _choose_mode() -> str:
    print("\n── Step 2: Usage mode ──")
    labels = [label for label, _ in MODE_CHOICES]
    label = _select("How will you primarily use this agent?", labels)
    return dict(MODE_CHOICES)[label]


# ── Mode A: ADK + local CSV ─────────────────────────────────────────────────


def _configure_adk_local(existing: dict[str, str]) -> tuple[dict[str, str], WizardSummary]:
    print("\n── ADK + local sample data ──")
    updates: dict[str, str] = {"RETAIL_DATA_SOURCE": "local_csv"}
    updates.update(PIPELINE_ADVANCED_DEFAULTS)

    sample = PROJECT_ROOT / SAMPLE_CSV_RELATIVE
    default_csv = existing.get("RETAIL_METRICS_CSV") or (
        SAMPLE_CSV_RELATIVE if sample.is_file() else ""
    )
    csv_path = _prompt("Path to sample CSV", default_csv)
    if csv_path:
        updates["RETAIL_METRICS_CSV"] = csv_path
        full = PROJECT_ROOT / csv_path
        if not full.is_file():
            _print_note(f"Warning: {full} not found — you can fix this in .env later.")

    summary = WizardSummary(
        mode=MODE_ADK_LOCAL,
        llm_provider_label="",
        llm_model="",
        data_source_label="Local CSV",
    )
    return updates, summary


# ── Mode B: ADK + MCP server ────────────────────────────────────────────────

_VENV_SUBDIRS_WIN = (".venv", "Scripts", "python.exe")
_VENV_SUBDIRS_UNIX = (".venv", "bin", "python")


def _auto_detect_mcp_python(server_dir: Path) -> str | None:
    """Find a venv Python in the MCP server directory."""
    for parts in [_VENV_SUBDIRS_WIN, _VENV_SUBDIRS_UNIX]:
        candidate = server_dir.joinpath(*parts)
        if candidate.is_file():
            return str(candidate)
    return None


def _configure_adk_mcp(existing: dict[str, str]) -> tuple[dict[str, str], WizardSummary]:
    print("\n── ADK + external MCP server ──")
    _print_note(
        "The MCP server is a separate project (not vendored into this repo). "
        "ADK spawns it via stdio and exposes its tools alongside the local pipeline."
    )
    _print_note(
        "Databricks credentials belong in the MCP server's own .env, not here."
    )

    updates: dict[str, str] = {"RETAIL_DATA_SOURCE": "local_csv"}
    updates.update(PIPELINE_ADVANCED_DEFAULTS)
    notes: list[str] = []

    default_path = existing.get("WFM_DQ_MCP_SERVER_PATH_FOR_ADK", "")
    while True:
        mcp_path = _prompt("Path to MCP server script (server.py)", default_path)
        if not mcp_path:
            _print_note("No path provided — MCP tools will be disabled in ADK.")
            break

        resolved = Path(mcp_path).resolve()
        if resolved.is_file():
            updates["WFM_DQ_MCP_SERVER_PATH_FOR_ADK"] = str(resolved)

            detected_py = _auto_detect_mcp_python(resolved.parent)
            if detected_py:
                _print_note(f"Auto-detected MCP server venv: {detected_py}")
                updates["WFM_DQ_MCP_PYTHON_FOR_ADK"] = detected_py
            else:
                _print_note(
                    "No venv found in the MCP server directory. "
                    "If the server has its own dependencies, set "
                    "WFM_DQ_MCP_PYTHON_FOR_ADK in .env to the correct Python path."
                )
                notes.append(
                    "Set WFM_DQ_MCP_PYTHON_FOR_ADK if MCP server needs a separate Python"
                )

            sample = PROJECT_ROOT / SAMPLE_CSV_RELATIVE
            if sample.is_file():
                updates["RETAIL_METRICS_CSV"] = SAMPLE_CSV_RELATIVE
            break
        else:
            print(f"  File not found: {resolved}")
            if _confirm("Skip MCP setup for now? (ADK will work with local pipeline only)", default=True):
                notes.append("MCP path not configured — ADK runs without MCP tools")
                break

    summary = WizardSummary(
        mode=MODE_ADK_MCP,
        llm_provider_label="",
        llm_model="",
        data_source_label="MCP server (ADK toolset)",
        mcp_adk_enabled="WFM_DQ_MCP_SERVER_PATH_FOR_ADK" in updates,
        extra_notes=notes,
    )
    return updates, summary


# ── Mode C: Developer / advanced ─────────────────────────────────────────────


def _configure_developer(existing: dict[str, str]) -> tuple[dict[str, str], WizardSummary]:
    """Full advanced wizard — exposes all pipeline, Slack, scheduler, and MCP settings."""
    updates: dict[str, str] = {}
    notes: list[str] = []

    ds_updates, ds_label = _configure_data_source(existing)
    updates.update(ds_updates)

    mcp_adk_on = False
    if _confirm("\nEnable MCP tools in ADK web? (requires external MCP server)", default=False):
        mcp_updates, mcp_adk_on = _configure_adk_mcp_for_dev(existing)
        updates.update(mcp_updates)

    slack_updates, slack_on = _configure_slack(existing)
    updates.update(slack_updates)

    sched_updates, sched_on = _configure_scheduler(existing)
    updates.update(sched_updates)

    adv_updates, adv_custom = _configure_advanced(existing)
    updates.update(adv_updates)

    summary = WizardSummary(
        mode=MODE_DEVELOPER,
        llm_provider_label="",
        llm_model="",
        data_source_label=ds_label,
        mcp_adk_enabled=mcp_adk_on,
        slack_enabled=slack_on,
        scheduler_enabled=sched_on,
        advanced_customized=adv_custom,
        extra_notes=notes,
    )
    return updates, summary


def _configure_data_source(existing: dict[str, str]) -> tuple[dict[str, str], str]:
    print("\n── Pipeline data source ──")
    ds_label = _select(
        "Where do daily metrics come from?",
        ["Local CSV file", "MCP server (stdio)", "Databricks MCP (HTTP)"],
    )
    updates: dict[str, str] = {}

    if ds_label == "Local CSV file":
        updates["RETAIL_DATA_SOURCE"] = "local_csv"
        sample = PROJECT_ROOT / SAMPLE_CSV_RELATIVE
        default_csv = existing.get("RETAIL_METRICS_CSV") or (
            SAMPLE_CSV_RELATIVE if sample.is_file() else ""
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

    elif ds_label == "MCP server (stdio)":
        updates["RETAIL_DATA_SOURCE"] = "mcp_server"
        default_server = existing.get("WFM_DQ_MCP_SERVER_PATH", "")
        path = _prompt("WFM_DQ_MCP_SERVER_PATH (path to server.py)", default_server)
        if path:
            updates["WFM_DQ_MCP_SERVER_PATH"] = path
        timeout = _prompt(
            "WFM_DQ_MCP_TIMEOUT_SECONDS",
            existing.get("WFM_DQ_MCP_TIMEOUT_SECONDS", "120"),
        )
        updates["WFM_DQ_MCP_TIMEOUT_SECONDS"] = timeout

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


def _configure_adk_mcp_for_dev(existing: dict[str, str]) -> tuple[dict[str, str], bool]:
    """Ask for ADK MCP settings in developer mode (compact)."""
    updates: dict[str, str] = {}
    default_path = existing.get("WFM_DQ_MCP_SERVER_PATH_FOR_ADK", "")
    mcp_path = _prompt("WFM_DQ_MCP_SERVER_PATH_FOR_ADK", default_path)
    if not mcp_path:
        return updates, False

    resolved = Path(mcp_path).resolve()
    if not resolved.is_file():
        _print_note(f"Warning: {resolved} not found. ADK will skip MCP tools at runtime.")

    updates["WFM_DQ_MCP_SERVER_PATH_FOR_ADK"] = str(resolved)

    detected_py = _auto_detect_mcp_python(resolved.parent)
    if detected_py:
        _print_note(f"Auto-detected MCP venv Python: {detected_py}")
        updates["WFM_DQ_MCP_PYTHON_FOR_ADK"] = detected_py
    else:
        py_path = _prompt(
            "WFM_DQ_MCP_PYTHON_FOR_ADK (optional — Python for MCP server)",
            existing.get("WFM_DQ_MCP_PYTHON_FOR_ADK", ""),
        )
        if py_path:
            updates["WFM_DQ_MCP_PYTHON_FOR_ADK"] = py_path
    return updates, True


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
        return dict(PIPELINE_ADVANCED_DEFAULTS), False

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


# ── Summary / confirmation ───────────────────────────────────────────────────

_MODE_LABELS = {
    MODE_ADK_LOCAL: "ADK web + local CSV",
    MODE_ADK_MCP: "ADK web + MCP server",
    MODE_DEVELOPER: "Developer / advanced",
}


def _print_confirmation(summary: WizardSummary, updates: dict[str, str]) -> None:
    mode_label = _MODE_LABELS.get(summary.mode, summary.mode)
    print("\n" + "=" * 60)
    print("Setup complete")
    print("=" * 60)
    print(f"  Config file:     {summary.env_path}")
    print(f"  Mode:            {mode_label}")
    print(f"  LLM:             {summary.llm_provider_label}")
    print(f"  Model:           {summary.llm_model}")
    print(f"  Data source:     {summary.data_source_label}")

    if summary.mode == MODE_ADK_MCP or summary.mcp_adk_enabled:
        print(f"  MCP in ADK:      {'enabled' if summary.mcp_adk_enabled else 'disabled'}")
    if summary.mode == MODE_DEVELOPER:
        print(f"  Slack:           {'enabled' if summary.slack_enabled else 'disabled'}")
        print(f"  Scheduler:       {'enabled' if summary.scheduler_enabled else 'disabled'}")
        print(
            f"  Pipeline tuning: "
            f"{'customized' if summary.advanced_customized else 'defaults'}"
        )

    if summary.extra_notes:
        print("\n  Notes:")
        for note in summary.extra_notes:
            print(f"    • {note}")

    print("\n  Environment keys written:")
    for key in sorted(updates):
        val = updates[key] or ""
        if any(s in key for s in ("KEY", "TOKEN", "WEBHOOK")):
            print(f"    {key}={mask_secret(val)}")
        else:
            print(f"    {key}={val}")

    print("\n  Next steps:")
    print("    adk web .                  # launch ADK chat UI")
    if summary.mode == MODE_DEVELOPER:
        print("    python run_day.py --date 2024-05-20")
        print("    python evaluate.py")
        print("    pytest tests -q")
    print("=" * 60)


# ── Main entry point ─────────────────────────────────────────────────────────


def run_wizard(env_path: Path = DEFAULT_ENV_PATH, *, interactive: bool = True) -> int:
    if not interactive:
        print("Non-interactive wizard: use interactive mode (default).", file=sys.stderr)
        return 1

    print("Retail Data Quality Agent — setup wizard")
    print("Configure your environment for ADK web, CLI, or both.\n")

    existing = parse_env_file(env_path)
    updates: dict[str, str | None] = {}

    # Step 1: LLM (all modes)
    llm_updates, provider_label, model = _configure_llm(existing)
    updates.update(llm_updates)

    # Step 2: Usage mode
    mode = _choose_mode()

    # Step 3: Mode-specific config
    if mode == MODE_ADK_LOCAL:
        mode_updates, summary = _configure_adk_local(existing)
    elif mode == MODE_ADK_MCP:
        mode_updates, summary = _configure_adk_mcp(existing)
    else:
        mode_updates, summary = _configure_developer(existing)

    updates.update(mode_updates)

    # Backfill summary with LLM info
    summary.llm_provider_label = provider_label
    summary.llm_model = model
    summary.env_path = env_path

    merge_env_file(env_path, updates)
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
