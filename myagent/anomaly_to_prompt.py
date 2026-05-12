# Serialize anomaly dicts into a structured, store-level block for the LLM.

from __future__ import annotations

from collections import Counter, defaultdict

_SEVERITY_RANK = {"High": 0, "Medium": 1, "Low": 2}

_ISSUE_SHORT = {
    "Continuity Gap": "Continuity",
    "Inconsistent Grain": "Grain",
    "Positive Spike": "Spike",
    "Negative Outlier": "Negative",
}


# Abbreviated label for issue_type in rollup summaries.
def _short_issue(issue_type: str) -> str:
    return _ISSUE_SHORT.get(issue_type, issue_type)


# Comma-separated counts of short issue labels across records.
def _rollup_issue_types(records: list[dict]) -> str:
    c = Counter(_short_issue(r.get("issue_type", "")) for r in records)
    parts = [f"{k} {v}" for k, v in sorted(c.items(), key=lambda x: (-x[1], x[0]))]
    return ", ".join(parts) if parts else "none"


# One key=value style line for an anomaly (machine-readable tail).
def _structured_line(rec: dict) -> str:
    d = rec.get("details", "").replace('"', "'")
    return (
        f"storeid={rec.get('storeid')}, deptname={rec.get('deptname')}, "
        f"metriccode={rec.get('metriccode')}, date_range={rec.get('date_or_range')}, "
        f"issue_type={rec.get('issue_type')}, severity={rec.get('severity')}, "
        f"impact_score={rec.get('impact_score')}, "
        f"estimated_revenue_at_risk={rec.get('estimated_revenue_at_risk')}, "
        f"customer_impact={rec.get('customer_impact')}, "
        f"operational_risk={rec.get('operational_risk')}, "
        f'details="{d}"'
    )


# Markdown sections by store/dept; top High/Medium lines + machine-readable list (needs enrich_anomalies fields).
def format_anomalies_for_llm(anomalies: list[dict]) -> str:
    if not anomalies:
        return (
            "No deterministic anomalies were detected in the supplied data window."
        )

    by_store_dept: dict[tuple[object, object], list[dict]] = defaultdict(list)
    for rec in anomalies:
        key = (rec.get("storeid"), rec.get("deptname"))
        by_store_dept[key].append(rec)

    lines: list[str] = []
    lines.append("## Anomalies by store / department")
    lines.append("")

    sorted_keys = sorted(
        by_store_dept.keys(),
        key=lambda k: (str(k[0]), str(k[1])),
    )

    machine_readable_lines: list[str] = []

    for store, dept in sorted_keys:
        group = by_store_dept[(store, dept)]
        sev_counts = Counter((r.get("severity") or "Low") for r in group)
        n_h = sev_counts.get("High", 0)
        n_m = sev_counts.get("Medium", 0)
        n_l = sev_counts.get("Low", 0)
        rollup = _rollup_issue_types(group)

        lines.append(
            f"### Store {store} – {dept}: {n_h} High, {n_m} Medium, {n_l} Low "
            f"({rollup})"
        )

        # Order by severity rank first, then higher impact_score.
        def sort_key(r: dict) -> tuple[int, float]:
            sev = r.get("severity") or "Low"
            return (_SEVERITY_RANK.get(sev, 2), -float(r.get("impact_score") or 0))

        high_med = [
            r
            for r in group
            if (r.get("severity") or "Low") in ("High", "Medium")
        ]
        low_only = [
            r
            for r in group
            if (r.get("severity") or "Low") == "Low"
        ]

        high_med_sorted = sorted(high_med, key=sort_key)
        detail_candidates = high_med_sorted
        if not detail_candidates and low_only:
            detail_candidates = sorted(
                low_only,
                key=lambda r: -float(r.get("impact_score") or 0),
            )

        for rec in detail_candidates[:3]:
            lines.append(
                f"- [{rec.get('severity')}] {rec.get('issue_type')}: "
                f"{rec.get('metriccode')} @ {rec.get('date_or_range')} "
                f"(impact={rec.get('impact_score')}, rev_risk={rec.get('estimated_revenue_at_risk')}, "
                f"cust={rec.get('customer_impact')}, ops={rec.get('operational_risk')}) — "
                f"{rec.get('details')}"
            )
            machine_readable_lines.append(_structured_line(rec))

        if len(high_med_sorted) > 3:
            lines.append(
                f"- … plus {len(high_med_sorted) - 3} more High/Medium issue(s) in this group "
                "(see machine-readable block below)."
            )
            for rec in high_med_sorted[3:]:
                machine_readable_lines.append(_structured_line(rec))

        if low_only:
            low_roll = _rollup_issue_types(low_only)
            if high_med_sorted:
                lines.append(
                    f"- Low-severity tail: {len(low_only)} issue(s) ({low_roll}); "
                    "summarize briefly or omit if voluminous."
                )
            elif len(low_only) > 3:
                lines.append(
                    f"- Low-severity tail: {len(low_only) - 3} additional issue(s) "
                    f"after the top 3 shown ({low_roll}); keep narrative short."
                )
        lines.append("")

    lines.append("## Anomalies (machine-readable; use severity & issue_type as given)")
    lines.append("")
    for ln in machine_readable_lines:
        lines.append(f"- {ln}")

    return "\n".join(lines).rstrip()
