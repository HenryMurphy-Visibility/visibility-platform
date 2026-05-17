"""
inspect_compute.py
──────────────────────────────────────────────────────────────────────────────
Direct inspect harness for all compute functions.
Run from chest root without starting the server.

Usage:
    python inspect_compute.py

Each inspect prints PASS or FAIL with the key numbers.
No server required. No reboot required.
Fix a bug, run again instantly.
──────────────────────────────────────────────────────────────────────────────
"""

import sys
import traceback
import pandas as pd
from datetime import datetime

# ── DISPLAY SETTINGS ─────────────────────────────────────────
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


def result_summary(name, result, key_fields=None):
    """Print a compact summary of a ComputeResult."""
    if result is None:
        print(f"{FAIL} {name} — returned None")
        return

    status = PASS if result.valid else FAIL
    rows   = len(result.data) if result.data is not None else 0
    ms     = result.metadata.get("elapsed_ms", "?")

    print(f"{status} {name}")
    print(f"       rows={rows} | valid={result.valid} | {ms}ms")

    if result.errors:
        print(f"       errors: {result.errors[:3]}")

    if key_fields and result.data is not None and not result.data.empty:
        print(f"       sample:")
        try:
            cols = [c for c in key_fields if c in result.data.columns]
            print(result.data[cols].head(3).to_string(index=False))
        except Exception as e:
            print(f"       (could not print sample: {e})")


# ============================================================
# LOAD PREP ONCE — reused by all inspects
# ============================================================

def load_prep():
    section("LOADING PREP STATE")
    from financial_information_gateway.fig_code.fig_core import prep_state
    try:
        prep = prep_state(PORTFOLIO, CALENDAR, PERIOD_START, PERIOD_END)
        n_je  = len(prep["journal_entries"])
        print(f"{PASS} prep_state loaded | {n_je} journal entries")
        print(f"       prior_cutoff  = {prep['prior_cutoff_datetime']}")
        print(f"       current_cutoff= {prep['current_cutoff_datetime']}")
        return prep
    except Exception as e:
        print(f"{FAIL} prep_state failed: {e}")
        traceback.print_exc()
        return None


# ============================================================
# TESTS
# ============================================================

def inspect_balance_sheet(prep):
    section("BALANCE SHEET")
    from financial_information_gateway.fig_code.compute_balance_sheet import compute_balance_sheet
    try:
        result = compute_balance_sheet(
            portfolio=PORTFOLIO, calendar=CALENDAR,
            period_start=PERIOD_START, period_end=PERIOD_END,
            uber_filter={"investment": INVESTMENT},
            prep=prep,
        )
        result_summary("compute_balance_sheet", result,
            key_fields=["investment", "financial_account", "section",
                        "open_book", "move_book", "close_book", "ties"])

        if result.data is not None and not result.data.empty:
            failures = result.data[
                (result.data.get("ties", True) == False) &
                (result.data.get("row_type", "detail") == "detail")
            ] if "ties" in result.data.columns else pd.DataFrame()
            print(f"       invariant failures: {len(failures)}")

    except Exception as e:
        print(f"{FAIL} compute_balance_sheet — {e}")
        traceback.print_exc()


def inspect_unrealized(prep):
    section("UNREALIZED")
    from financial_information_gateway.fig_code.compute_unrealized import compute_unrealized
    try:
        result = compute_unrealized(
            portfolio=PORTFOLIO, calendar=CALENDAR,
            period_start=PERIOD_START, period_end=PERIOD_END,
            uber_filter={"investment": INVESTMENT},
            prep=prep,
        )
        result_summary("compute_unrealized", result,
            key_fields=["investment", "unreal_total_book_je",
                        "unreal_total_book_state", "total_diff", "ties"])

        all_clear = result.metadata.get("all_ties", False)
        print(f"       all_ties: {all_clear}")

    except Exception as e:
        print(f"{FAIL} compute_unrealized — {e}")
        traceback.print_exc()


def inspect_realized_gains(prep):
    section("REALIZED GAINS")
    from financial_information_gateway.fig_code.compute_realized import compute_realized_gains
    try:
        result = compute_realized_gains(
            portfolio=PORTFOLIO, calendar=CALENDAR,
            period_start=PERIOD_START, period_end=PERIOD_END,
            uber_filter={"investment": INVESTMENT},
            prep=prep,
        )
        result_summary("compute_realized_gains", result,
            key_fields=["investment", "ibor_date",
                        "realized_price_book", "realized_fx_book",
                        "realized_total_book"])

    except Exception as e:
        print(f"{FAIL} compute_realized_gains — {e}")
        traceback.print_exc()


def inspect_income(prep):
    section("INCOME")
    from financial_information_gateway.fig_code.compute_income import compute_income
    try:
        result = compute_income(
            portfolio=PORTFOLIO, calendar=CALENDAR,
            period_start=PERIOD_START, period_end=PERIOD_END,
            uber_filter={"investment": INVESTMENT},
            prep=prep,
            shape="summary",
        )
        result_summary("compute_income", result,
            key_fields=["investment", "income_type",
                        "income_local", "income_book"])

    except Exception as e:
        print(f"{FAIL} compute_income — {e}")
        traceback.print_exc()


def inspect_capital(prep):
    section("CAPITAL")
    from financial_information_gateway.fig_code.compute_capital import compute_capital
    try:
        result = compute_capital(
            portfolio=PORTFOLIO, calendar=CALENDAR,
            period_start=PERIOD_START, period_end=PERIOD_END,
            uber_filter={"investment": INVESTMENT},
            prep=prep,
            shape="summary",
        )
        result_summary("compute_capital", result,
            key_fields=["investment", "net_book", "flow_type"])

    except Exception as e:
        print(f"{FAIL} compute_capital — {e}")
        traceback.print_exc()


def inspect_recon(prep):
    section("RECON")
    from financial_information_gateway.fig_code.compute_recon import compute_recon
    try:
        result = compute_recon(
            portfolio=PORTFOLIO, calendar=CALENDAR,
            period_start=PERIOD_START, period_end=PERIOD_END,
            uber_filter={"investment": INVESTMENT},
            prep=prep,
            include_view1=True,
            include_view2=True,
            include_view3=False,
            include_cross_view=True,
        )

        result_summary("compute_recon", result,
            key_fields=["investment", "opening_nav", "capital_flows",
                        "income", "realized_gains", "unreal_change",
                        "computed_closing", "actual_closing",
                        "nav_diff", "nav_ties"])

        all_clear = result.metadata.get("all_clear", False)
        print(f"\n  >>> ALL CLEAR: {all_clear} <<<")

    except Exception as e:
        print(f"{FAIL} compute_recon — {e}")
        traceback.print_exc()


def inspect_performance(prep):
    section("PERFORMANCE")
    from financial_information_gateway.fig_code.compute_performance import compute_performance
    try:
        result = compute_performance(
            portfolio=PORTFOLIO, calendar=CALENDAR,
            period_start=PERIOD_START, period_end=PERIOD_END,
            level="investment",
            cadence="D",
            uber_filter={"investment": INVESTMENT},
            prep=prep,
        )
        result_summary("compute_performance", result,
            key_fields=["investment", "ibor_date",
                        "BMV_Book", "EMV_Book",
                        "TWR_Book", "Index_Book"])

    except Exception as e:
        print(f"{FAIL} compute_performance — {e}")
        traceback.print_exc()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    prep = load_prep()

    if prep is None:
        print("\nCannot continue — prep_state failed.")
        sys.exit(1)

    # ── TEMP DIAGNOSTIC ──────────────────────────────────────
    print("\n--- MarketVal JEs for USD ---")
    count = 0
    for je in prep["journal_entries"]:
        if getattr(je, "investment", None) == "USD" and \
                getattr(je, "financial_account", None) == "MarketVal":
            book = getattr(je, "book", None) or 0.0
            ibor = getattr(je, "ibor_date", None)
            print(f"  {ibor} | book={book:,.2f}")
            count += 1
            if count >= 5:
                print("  ...")
                break
    print(f"  Total MarketVal JEs for USD: {count}")

    inspect_balance_sheet(prep)
    inspect_unrealized(prep)
    inspect_realized_gains(prep)
    inspect_income(prep)
    inspect_capital(prep)
    inspect_recon(prep)
    inspect_performance(prep)
