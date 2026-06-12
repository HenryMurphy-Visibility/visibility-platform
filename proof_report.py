# -*- coding: utf-8 -*-
"""
proof_report.py — Readable renderer for the VAI Proof Engine
══════════════════════════════════════════════════════════════════════════════
Consumes the list[ProofResult] that run_proof() already returns and prints a
parsed, human-readable report. Does NOT modify the proof engine or its logic —
it only re-presents the structured results.

Usage:
    from proof_engine import run_proof
    from proof_report import render_report

    results = run_proof("Portfolio2", "Monthly")   # engine prints its own grid
    render_report(results)                          # then the readable layer

Or one-shot:
    from proof_report import run_and_report
    run_and_report("Portfolio2", "Monthly")

What it does that the raw output doesn't:
  • Collapses cascades — one missing price shown once with its N effects, not N times
  • Buckets findings: DATA GAPS (fix the data) vs INTEGRITY (investigate the logic)
  • Translates D-codes and the MV-mismatch block into plain English
  • Surfaces the few things that actually need a human, hides the noise
"""

import re
from collections import defaultdict, OrderedDict

# Reuse the engine's colors if available; fall back to plain.
try:
    from proof_engine import GREEN, YELLOW, RED, CYAN, BLUE, RESET, BOLD, DIM
except Exception:
    GREEN = YELLOW = RED = CYAN = BLUE = RESET = BOLD = DIM = ""


# ── classify a failure/warning message into a category ────────────────────────
# Each entry: (regex, bucket, short_label, plain_translation_template)
#   bucket: "DATA" (missing inputs — fix data) | "INTEGRITY" (logic — investigate)
_PATTERNS = [
    (re.compile(r"Price missing"),            "DATA",      "Missing price",
     "No price in price_master for this name on the period-end date."),
    (re.compile(r"FX missing"),               "DATA",      "Missing FX rate",
     "No FX rate in fx_master for this currency on the settle/period date."),
    (re.compile(r"no price for MV check"),    "DATA",      "Mark skipped (no price)",
     "Mark check couldn't run — same missing price as above."),
    (re.compile(r"no FX .* for MV check"),    "DATA",      "Mark skipped (no FX)",
     "Mark check couldn't run — missing FX rate for this currency."),
    (re.compile(r"Price gap"),                "DATA",      "Stale price",
     "Price found, but not on the exact date — an earlier date was used."),
    (re.compile(r"FX gap"),                   "DATA",      "Stale FX rate",
     "FX rate found, but not on the exact date — an earlier date was used."),

    (re.compile(r"MVBase MISMATCH"),          "INTEGRITY", "Mark mismatch",
     "Market value computed two ways disagree (price×qty vs cost+unrealized)."),
    (re.compile(r"out of balance"),           "INTEGRITY", "Journal imbalance",
     "Debits and credits don't net to zero for the period."),
    (re.compile(r"D-005 duplicate JE"),       "INTEGRITY", "Duplicate JE",
     "Two journal entries share the same key (could be a legit offset pair)."),
    (re.compile(r"D-006 MarketVal=0"),        "INTEGRITY", "Active position, no MV",
     "Position has cost but zero market value (often the same missing-price cause)."),
    (re.compile(r"D-001"),                    "INTEGRITY", "kdbegin≠tradedate",
     "Known-date begin doesn't equal the trade date."),
    (re.compile(r"D-002"),                    "INTEGRITY", "kdbegin<tradedate",
     "Known-date begin is before the trade date."),
    (re.compile(r"D-003"),                    "INTEGRITY", "Holiday tradedate",
     "Trade date falls on a weekend or NYSE holiday."),
    (re.compile(r"D-004"),                    "INTEGRITY", "Settle<trade",
     "Settle date is before the trade date."),
    (re.compile(r"D-007"),                    "INTEGRITY", "Zero quantity",
     "Buy/sell event has zero quantity."),
    (re.compile(r"D-008"),                    "INTEGRITY", "Zero/neg price",
     "Buy/sell event has a zero or negative price."),
    (re.compile(r"D-009"),                    "INTEGRITY", "Amount mismatch",
     "total_amount doesn't equal qty × price."),
    (re.compile(r"Unknown account"),          "INTEGRITY", "Unknown account",
     "A journal posted to an account not in the chart of accounts."),
    (re.compile(r"FX G/L mismatch"),          "INTEGRITY", "Settle FX G/L wrong",
     "Realized trade/settle FX gain/loss doesn't match the rate move."),
]

_PILLAR_LABEL = {
    "availability":      "1 · Data Availability",
    "balance":           "2 · Journal Balance",
    "settle_fx":         "3 · Trade/Settle FX",
    "marks":             "4 · Mark Verification",
    "chart_of_accounts": "5 · Chart of Accounts",
    "data":              "6 · Data Integrity",
}


def _classify(message: str):
    for rx, bucket, label, plain in _PATTERNS:
        if rx.search(message):
            return bucket, label, plain
    return "INTEGRITY", "Other", ""   # default: treat unknowns as worth a look


_DCODE = re.compile(r"\bD-\d{3}\b")

def _investment_of(item):
    """Best-effort instrument name for grouping a cascade."""
    inv = (getattr(item, "investment", "") or "").strip()
    if inv:
        return inv
    msg = _DCODE.sub("", item.message)        # strip D-005 etc so it isn't mistaken for a ticker
    # "duplicate JE: USD 2026-01-06 Cost ..." / "active position: JPY on ..."
    m = re.search(r"(?:position:|JE:)\s*([A-Z0-9]{1,6}(?:\.[A-Z])?)", msg)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z]{2,6}(?:\.[A-Z])?)\b", msg)
    return m.group(1) if m else ""


_DATE_IN_MSG = re.compile(r"\b(\d{4}-\d{2}(?:-\d{2})?)\b")

def _period_of(item):
    """Period from the field, falling back to a date parsed from the message."""
    p = (getattr(item, "period", "") or "").strip()
    if p:
        return p
    m = _DATE_IN_MSG.search(item.message)
    return m.group(1) if m else "?"


def render_report(results: list, show_mismatch_detail: bool = True) -> None:
    """Print the readable, cascade-collapsed report from run_proof() results."""

    # ── 1. one-line verdict per pillar ────────────────────────────────────────
    print(f"\n{BOLD}{'═'*72}{RESET}")
    print(f"{BOLD}  PROOF — READABLE SUMMARY{RESET}")
    print(f"{BOLD}{'═'*72}{RESET}")
    print(f"  {'PILLAR':<26}{'VERDICT':<9}{'pass':>6}{'warn':>6}{'fail':>6}")
    print(f"  {'─'*68}")
    for r in results:
        label   = _PILLAR_LABEL.get(r.pillar, r.pillar)
        clear   = r.all_clear
        vtxt    = "PASS" if clear else "FAIL"
        vcol    = GREEN if clear else RED
        print(f"  {label:<26}{vcol}{vtxt:<9}{RESET}"
              f"{len(r.passes):>6}{len(r.warnings):>6}{len(r.failures):>6}")
    print(f"  {'─'*68}")

    # ── 2. gather every failure + warning, classify, collapse by cause ────────
    data_gaps   = defaultdict(lambda: defaultdict(list))   # label -> inv -> [periods]
    integrity   = defaultdict(list)                        # label -> [items]
    mismatch_detail = []                                   # full MV-mismatch blocks

    for r in results:
        for item in (r.failures + r.warnings):
            bucket, label, plain = _classify(item.message)
            inv = _investment_of(item)
            if bucket == "DATA":
                data_gaps[label][inv].append(_period_of(item))
            else:
                integrity[label].append(item)
                if label == "Mark mismatch" and show_mismatch_detail:
                    mismatch_detail.append(item)

    total_data = sum(len(p) for inv in data_gaps.values() for p in inv.values())
    total_intg = sum(len(v) for v in integrity.values())

    if total_data == 0 and total_intg == 0:
        print(f"\n{GREEN}{BOLD}  ✓ Nothing to review — all pillars clear.{RESET}\n")
        return

    # ── 3. DATA GAPS — collapsed: one line per (cause, instrument) ────────────
    if data_gaps:
        print(f"\n{BOLD}{YELLOW}  DATA GAPS{RESET}  {DIM}(fix the data — these are inputs, not logic){RESET}")
        for label in sorted(data_gaps):
            plain = next((p for rx, b, l, p in _PATTERNS if l == label), "")
            print(f"\n    {YELLOW}▸ {label}{RESET}  {DIM}{plain}{RESET}")
            for inv in sorted(data_gaps[label]):
                periods = sorted(set(data_gaps[label][inv]))
                shown   = ", ".join(periods[:6]) + (f" … (+{len(periods)-6} more)" if len(periods) > 6 else "")
                name    = inv or "(unattributed)"
                print(f"        {name:<10} {len(periods)} date(s): {shown}")

    # ── 4. INTEGRITY — the things that need a human ───────────────────────────
    if integrity:
        print(f"\n{BOLD}{RED}  INTEGRITY{RESET}  {DIM}(investigate — logic or data correctness){RESET}")
        for label in sorted(integrity):
            items = integrity[label]
            plain = next((p for rx, b, l, p in _PATTERNS if l == label), "")
            # collapse by instrument where it helps
            by_inv = defaultdict(list)
            for it in items:
                by_inv[_investment_of(it)].append(it)
            print(f"\n    {RED}▸ {label}{RESET} ({len(items)})  {DIM}{plain}{RESET}")
            for inv in sorted(by_inv):
                periods = sorted({_period_of(it) for it in by_inv[inv]})
                name    = inv or "(unattributed)"
                print(f"        {name:<10} {len(by_inv[inv])}× — periods: {', '.join(periods[:6])}")

    # ── 5. MARK-MISMATCH DETAIL — the real reconciliation puzzle ──────────────
    if mismatch_detail:
        print(f"\n{BOLD}{CYAN}  MARK-MISMATCH DETAIL{RESET}  {DIM}(the two valuation paths disagree){RESET}")
        for it in mismatch_detail:
            print(f"\n    {CYAN}• {it.period} · {it.investment}{RESET}")
            # the engine packs a multi-line block; normalize each line's indent
            body = it.message
            if "MISMATCH" in body:
                body = body.split("MISMATCH", 1)[-1]
            for line in body.splitlines():
                line = line.strip()
                if line:
                    print(f"      {line}")

    # ── 6. bottom line: how many ROOT issues vs raw lines ─────────────────────
    root_data = sum(len(inv) for inv in data_gaps.values())   # distinct (cause,inv)
    root_intg = len(integrity)                                # distinct integrity causes
    raw_lines = total_data + total_intg
    print(f"\n{BOLD}{'─'*72}{RESET}")
    print(f"  {raw_lines} raw findings collapse to "
          f"{BOLD}{root_data} data-gap cause(s){RESET} + "
          f"{BOLD}{root_intg} integrity issue(s){RESET} to review.")
    if data_gaps:
        print(f"  {DIM}Most data gaps share one root (a missing price/FX cascades into "
              f"availability, marks, and D-006).{RESET}")
    print()


def run_and_report(portfolio, calendar, period=None, **kw):
    """Convenience: run the engine quietly-ish, then render the readable layer."""
    from proof_engine import run_proof
    results = run_proof(portfolio, calendar, period=period, **kw)
    render_report(results)
    return results