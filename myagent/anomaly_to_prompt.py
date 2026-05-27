# Compact anomaly-to-prompt serialization for LLM summarization.
#
# Handles two shapes of anomaly data:
#   1. Local pipeline output — fields like storeid, deptname, metriccode, impact_score
#   2. External MCP server output — fields like store_id, dept_desc, metric_cd,
#      plus optional rich fields: continuity_scope, negative_magnitude,
#      csv_value, expected_value, priority, severity_reason, etc.
#
# The formatter gracefully degrades when richer fields are absent.

from __future__ import annotations

from collections import Counter, defaultdict

_SEV_RANK = {"High": 0, "Medium": 1, "Low": 2}


# ---------------------------------------------------------------------------
# Field accessors — normalize across local-pipeline and MCP shapes
# ---------------------------------------------------------------------------


def _store(rec: dict):
    return rec.get("store_id") or rec.get("storeid")


def _dept(rec: dict) -> str:
    return str(rec.get("dept_desc") or rec.get("deptname") or "?")


def _metric(rec: dict) -> str:
    return str(rec.get("metric_cd") or rec.get("metriccode") or "?")


def _severity(rec: dict) -> str:
    return str(rec.get("severity") or "Low")


def _priority(rec: dict) -> float:
    """Return numeric priority (lower = more important). Falls back to severity rank."""
    p = rec.get("priority")
    if p is not None:
        try:
            return float(p)
        except (TypeError, ValueError):
            pass
    return float(_SEV_RANK.get(_severity(rec), 2) * 100)


def _issue(rec: dict) -> str:
    return str(rec.get("issue_type") or "?")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_anomalies_for_llm(anomalies: list[dict]) -> str:
    """Serialize anomalies into a compact, grouped prompt block.

    Uses priority for ordering when available, otherwise falls back to
    severity + impact_score. Recognizes both local-pipeline and MCP field
    names. Includes richer context (scope, magnitude, error%) when present.
    """
    if not anomalies:
        return "No anomalies detected."

    sorted_all = sorted(anomalies, key=_priority)

    scope = _scope_header(sorted_all)
    body = _format_body(sorted_all)

    parts = []
    if scope:
        parts.append(scope)
    parts.append(body)
    return "\n".join(parts)


def format_anomalies_for_llm_by_issue(
    anomalies: list[dict],
    issue_filter: str | None = None,
) -> str:
    """Format anomalies filtered to a specific issue type.

    Useful when the agent wants to answer a targeted question (e.g. only
    continuity gaps, only negative outliers, only derived mismatches).
    """
    if issue_filter:
        key = issue_filter.lower()
        filtered = [a for a in anomalies if key in _issue(a).lower()]
        if not filtered:
            return f"No {issue_filter} anomalies found."
        return format_anomalies_for_llm(filtered)
    return format_anomalies_for_llm(anomalies)


# ---------------------------------------------------------------------------
# Scope summary (optional — only when MCP provides scope_summary or
# continuity_scope fields)
# ---------------------------------------------------------------------------


def _scope_header(anomalies: list[dict]) -> str:
    """Build a one-line scope summary if the data supports it."""
    # Check if any anomaly has MCP-style scope_summary at the response level
    # (would be passed down by the caller). Absent = skip.
    scopes = [a.get("continuity_scope") for a in anomalies if a.get("continuity_scope")]
    if not scopes:
        return ""

    scope_counts = Counter(scopes)
    parts = []
    for scope in ("systemic", "multi_store", "isolated"):
        cnt = scope_counts.get(scope, 0)
        if cnt:
            label = scope.replace("_", "-")
            parts.append(f"{cnt} {label}")
    if parts:
        return f"Continuity breakdown: {', '.join(parts)}"
    return ""


# ---------------------------------------------------------------------------
# Body formatting
# ---------------------------------------------------------------------------


def _format_body(anomalies: list[dict]) -> str:
    """Render compact bullet lines grouped by store/dept."""
    by_group: dict[tuple, list[dict]] = defaultdict(list)
    for rec in anomalies:
        by_group[(_store(rec), _dept(rec))].append(rec)

    lines: list[str] = []
    for (store, dept), group in sorted(by_group.items(), key=lambda kv: _priority(kv[1][0])):
        sev = Counter(_severity(r) for r in group)
        header = (
            f"Store {store} / {dept}: "
            f"{sev.get('High', 0)}H {sev.get('Medium', 0)}M {sev.get('Low', 0)}L"
        )
        lines.append(header)

        for rec in sorted(group, key=_priority):
            lines.append(_compact_line(rec))

    return "\n".join(lines)


def _compact_line(rec: dict) -> str:
    """One bullet per anomaly with issue-type-specific compact facts."""
    sev = _severity(rec)
    issue = _issue(rec)
    metric = _metric(rec)

    parts = [f"- [{sev}] {issue}: {metric}"]

    reason = rec.get("severity_reason")
    if reason:
        parts.append(reason)
    else:
        fact = _pick_fact(rec)
        if fact:
            parts.append(fact)

    return " | ".join(parts)


def _pick_fact(rec: dict) -> str:
    """Return the single most informative supporting fact for this anomaly type."""
    issue = _issue(rec)

    if issue == "Continuity Gap":
        return _continuity_fact(rec)
    if issue == "Negative Outlier":
        return _negative_fact(rec)
    if issue == "Derived Metric Mismatch":
        return _derived_fact(rec)
    if issue == "Positive Spike":
        z = rec.get("z_score")
        if isinstance(z, (int, float)):
            return f"z={z:.1f}"
    if issue == "Volume Drop":
        pct = rec.get("drop_pct")
        if pct is not None:
            return f"drop={pct}%"
    if issue == "Inconsistent Grain":
        return "absent today"

    impact = rec.get("impact_score")
    if impact and str(impact) not in ("0", "0.0", "N/A", ""):
        return f"impact={impact}"
    return ""


def _continuity_fact(rec: dict) -> str:
    """Compact fact for continuity gaps — scope-aware when fields exist."""
    parts = []
    streak = rec.get("consecutive_missing_days") or rec.get("streak_length")
    if streak:
        parts.append(f"{streak}d gap")

    scope = rec.get("continuity_scope")
    if scope:
        label = scope.replace("_", "-")
        count = rec.get("affected_store_count")
        if count and count > 1:
            parts.append(f"{label} ({count} stores)")
        else:
            parts.append(label)
    else:
        first = rec.get("first_missing_date")
        last = rec.get("last_missing_date") or rec.get("last_missing")
        if first and last:
            parts.append(f"{first} to {last}")

    return ", ".join(parts) if parts else ""


def _negative_fact(rec: dict) -> str:
    """Compact fact for negatives — magnitude-aware when fields exist."""
    mag = rec.get("negative_magnitude")
    val = rec.get("metric_value") or rec.get("metricvalue")
    ratio = rec.get("historical_ratio")
    mean = rec.get("historical_mean")

    parts = []
    if mag is not None:
        parts.append(f"val={-mag}")
    elif val is not None:
        parts.append(f"val={val}")

    if ratio is not None:
        parts.append(f"{ratio}x hist mean")
    elif mean is not None:
        parts.append(f"mean={mean}")

    return ", ".join(parts) if parts else ""


def _derived_fact(rec: dict) -> str:
    """Compact fact for derived mismatches — shows csv vs expected when available."""
    csv_val = rec.get("csv_value") or rec.get("metric_value") or rec.get("metricvalue")
    exp_val = rec.get("expected_value") or rec.get("computed_value")
    err_pct = rec.get("error_pct") or rec.get("relative_error_pct")
    comps = rec.get("component_metric_codes")

    parts = []
    if csv_val is not None and exp_val is not None:
        parts.append(f"stored={csv_val} expected={exp_val}")
    if err_pct is not None:
        parts.append(f"err={err_pct}%")
    if comps:
        parts.append(f"components={'+'.join(str(c) for c in comps)}")

    return ", ".join(parts) if parts else ""
