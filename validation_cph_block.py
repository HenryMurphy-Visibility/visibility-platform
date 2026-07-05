"""
validation_cph_block.py
Visibility Platform — Line 2 Validation Block for CPH

Paste this into cph_run_and_materialize(), between the
Pass 1A load step and the first core_schedule_events() call.

It runs once per period, validates all qualifying events,
logs findings to metrics, and halts on hard errors before
any scheduling occurs.

INSERTION POINT in cph_run_and_materialize():

    mark("t_pass1a_load_end")           ← already exists

    # ── LINE 2 VALIDATION ──────────────  ← INSERT HERE
    mark("t_validate_start")
    validation_findings = _validate_events_line2(
        events   = events,
        portfolio = portfolio,
        period   = per_period_ctx["period_name"],
        metrics  = metrics,
    )
    mark("t_validate_end")
    # ───────────────────────────────────

    scheduler = EventScheduler(space)   ← already exists

Also add to imports at top of your CPH file:
    from cph_validation_block import _validate_events_line2
"""

# ============================================================
# IMPORTS
# ============================================================

from validation_engine    import validate_event
from validation_functions import event_row_to_payload


# ============================================================
# LINE 2 VALIDATION
# ============================================================

def _validate_events_line2(
    events:    list,
    portfolio: str,
    period:    str,
    metrics:   dict,
) -> dict:
    """
    Validate all qualifying events before scheduling begins.

    - Errors   → appended to metrics, RuntimeError raised to halt CPH
    - Warnings → appended to metrics, processing continues
    - Info     → silently ignored

    Args:
        events:    List of raw event dicts (CSV field names, CSV date format)
        portfolio: Portfolio ID — for logging context
        period:    Period name — for logging context
        metrics:   CPH metrics dict — findings written here

    Returns:
        Summary dict written into metrics["validation"]
    """

    errors   = []
    warnings = []

    for event in events:
        tranid = event.get("tranid", "?")
        method = event.get("method", "?")

        # Convert CSV row to validation payload
        payload = event_row_to_payload(event)

        # Context available at CPH level — no AIF state yet
        context = {
            "portfolio":   portfolio,
            "period":      period,
        }

        # Run Line 2 validation
        report = validate_event(
            method  = method,
            payload = payload,
            context = context,
            line    = 2,
        )

        # Collect findings with event identity
        for finding in report.findings:
            entry = {
                "tranid":   tranid,
                "method":   method,
                "field":    finding.field,
                "rule":     finding.rule,
                "message":  finding.message,
                "severity": finding.severity,
            }
            if finding.severity == "error":
                errors.append(entry)
                print(
                    f"  ✗ LINE2 ERROR   | tranid={tranid} | {method} | "
                    f"[{finding.field}] {finding.message}"
                )
            elif finding.severity == "warning":
                warnings.append(entry)
                print(
                    f"  ⚠ LINE2 WARNING | tranid={tranid} | {method} | "
                    f"[{finding.field}] {finding.message}"
                )

    # Write summary to metrics
    summary = {
        "events_validated": len(events),
        "errors":           errors,
        "warnings":         warnings,
        "error_count":      len(errors),
        "warning_count":    len(warnings),
        "passed":           len(errors) == 0,
    }
    metrics["validation"] = summary

    # Print summary block consistent with CPH profile style
    print(f"\n{'✓' if summary['passed'] else '✗'} LINE 2 VALIDATION "
          f"| {portfolio} | {period} "
          f"| {len(events)} events "
          f"| {len(errors)} errors "
          f"| {len(warnings)} warnings")

    # Hard stop on errors — before any scheduling occurs
    if errors:
        error_summary = " | ".join(
            f"tranid={e['tranid']} [{e['field']}] {e['message']}"
            for e in errors[:5]  # first 5 only to keep message readable
        )
        raise RuntimeError(
            f"LINE 2 VALIDATION FAILED | {portfolio} | {period} | "
            f"{len(errors)} error(s): {error_summary}"
        )

    return summary