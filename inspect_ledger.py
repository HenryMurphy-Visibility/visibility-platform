# ============================================================
# inspect_ledger.py
# Direct test of compute_accounting_ledger — no prep passing.
# Mirrors exactly what the API console does.
# Run from PyCharm — right-click → Run 'inspect_ledger'
# ============================================================

import sys
import traceback
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 220)
pd.set_option("display.float_format", "{:,.2f}".format)

# ── INPUTS ────────────────────────────────────────────────────
PORTFOLIO    = "Portfolio1"
CALENDAR     = "Monthly"
PERIOD_START = "2021-01"
PERIOD_END   = "2021-01"
INVESTMENT   = None        # None = full portfolio, "GOOG" = single

if __name__ == "__main__":

    print("\n" + "=" * 70)
    print("  ACCOUNTING LEDGER INSPECT")
    print(f"  {PORTFOLIO} | {CALENDAR} | {PERIOD_START} → {PERIOD_END}")
    print(f"  Investment: {INVESTMENT if INVESTMENT else 'ALL'}")
    print("=" * 70)

    from financial_information_gateway.fig_code.compute_accounting_ledger import (
        compute_accounting_ledger,
    )

    uber_filter = {"investment": INVESTMENT} if INVESTMENT else None

    try:
        result = compute_accounting_ledger(
            portfolio=PORTFOLIO,
            calendar=CALENDAR,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            uber_filter=uber_filter,
        )

        df = result.data
        rows = len(df) if df is not None else 0

        print(f"\n  rows={rows} | valid={result.valid}")
        print(f"  metadata: {result.metadata}")

        if df is not None and not df.empty:
            print(f"\n  COLUMNS: {list(df.columns)}")
            print(f"\n  FIRST 20 ROWS:")
            cols = [c for c in
                    ["investment", "financial_account", "event_type",
                     "qty", "local", "book"]
                    if c in df.columns]
            print(df[cols].head(20).to_string(index=False))

            print(f"\n  CLOSING BALANCES BY INVESTMENT:")
            closing = df[df["event_type"] == "CLOSING"]
            if not closing.empty:
                summary = (
                    closing.groupby("investment")[["qty", "local", "book"]]
                    .sum()
                    .reset_index()
                )
                print(summary.to_string(index=False))
        else:
            print("  NO DATA RETURNED")

    except Exception as e:
        print(f"\n  FAILED: {e}")
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("  DONE")
    print("=" * 70 + "\n")