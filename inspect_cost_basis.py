# ============================================================
# inspect_cost_basis.py
# Quick test harness for compute_cost_basis.
# Run directly from PyCharm — right-click → Run 'inspect_cost_basis'
# ============================================================

import sys
import traceback
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)
pd.set_option("display.float_format", "{:,.4f}".format)

# ── TEST PARAMETERS ───────────────────────────────────────────
PORTFOLIO    = "Portfolio1"
CALENDAR     = "Monthly"
PERIOD_START = "2021-01"
PERIOD_END   = "2021-01"
INVESTMENT   = "GOOG"

PASS = "✓ PASS"
FAIL = "✗ FAIL"


def section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def load_prep():
    section("LOADING PREP STATE")
    from financial_information_gateway.fig_code.fig_core import prep_state
    try:
        prep = prep_state(PORTFOLIO, CALENDAR, PERIOD_START, PERIOD_END)
        n_je = len(prep["journal_entries"])
        print(f"{PASS} prep_state loaded | {n_je} journal entries")
        print(f"       prior_cutoff   = {prep['prior_cutoff_datetime']}")
        print(f"       current_cutoff = {prep['current_cutoff_datetime']}")
        return prep
    except Exception as e:
        print(f"{FAIL} prep_state failed: {e}")
        traceback.print_exc()
        return None


def inspect_cost_basis(prep):
    section("COST BASIS")
    from financial_information_gateway.fig_code.compute_cost_basis import compute_cost_basis
    try:
        result = compute_cost_basis(
            portfolio=PORTFOLIO, calendar=CALENDAR,
            period_start=PERIOD_START, period_end=PERIOD_END,
            uber_filter={"investment": INVESTMENT} if INVESTMENT is not None else None
        #    prep=prep,
        )

        rows   = len(result.data) if result.data is not None else 0
        ms     = result.metadata.get("elapsed_ms", "?")
        status = PASS if result.valid else FAIL

        print(f"{status} compute_cost_basis")
        print(f"       rows={rows} | valid={result.valid} | {ms}ms")
        print(f"       rows_after_filter={result.metadata.get('rows_after_filter')}")

        if result.errors:
            print(f"       errors: {result.errors[:3]}")

        if result.data is not None and not result.data.empty:
            cols = [c for c in
                    ["investment", "financial_account", "event_type",
                     "qty", "local", "book"]
                    if c in result.data.columns]
            print(f"\n       sample:")
            print(result.data[cols].head(10).to_string(index=False))

            # Summary by financial_account
            if "financial_account" in result.data.columns:
                summary = (
                    result.data[result.data["event_type"] == "ACTIVITY"]
                    .groupby("financial_account")[["qty", "local", "book"]]
                    .sum()
                    .reset_index()
                )
                if not summary.empty:
                    print(f"\n       activity summary by account:")
                    print(summary.to_string(index=False))

    except Exception as e:
        print(f"{FAIL} compute_cost_basis — {e}")
        traceback.print_exc()


if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("  COST BASIS INSPECT")
    print(f"  {PORTFOLIO} | {CALENDAR} | {PERIOD_START} → {PERIOD_END}")
    print(f"  Investment: {INVESTMENT}")
    print("=" * 60)

    prep = load_prep()

    if prep is None:
        print("\nCannot continue — prep_state failed.")
        sys.exit(1)

    inspect_cost_basis(prep)

    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60 + "\n")