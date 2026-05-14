# ============================================================
# inspect_journals.py
# Reads raw journal pickle files directly.
# Shows journal entries sorted by financial_account
# with detail rows and summary totals per account.
# ============================================================

import pickle
from pathlib import Path
from collections import defaultdict
from v_config import FUNDS_PATH

# ── INPUTS ──────────────────────────────────────────────────
PORTFOLIO  = "Portfolio1"
CALENDAR   = "Monthly"
PERIOD     = "2021-01"
INVESTMENT = "GOOG"

# Accounts to exclude from output
EXCLUDE_ACCOUNTS = {
    "UnrealPriceGLOffset",
    "UnrealFXGLOffset",
    "PriceGainStatOffset",
    "FXGainStatOffset",
}

# ── LOCATE JOURNALS DIRECTORY ───────────────────────────────
journals_dir = (
    Path(FUNDS_PATH)
    / PORTFOLIO
    / "Calendars"
    / CALENDAR
    / "Journals"
)

print(f"\nJournals directory: {journals_dir}")
print(f"Exists: {journals_dir.exists()}\n")

# ── LOAD ─────────────────────────────────────────────────────
for suffix in ["regular", "adjusting"]:

    print(f"{'='*60}")
    print(f"  {PERIOD} {suffix.upper()}")
    print(f"{'='*60}")

    matches = [
        f for f in journals_dir.glob("*.pkl")
        if suffix in f.name and PERIOD in f.name
    ]

    if not matches:
        print(f"  No {suffix} file found for {PERIOD}\n")
        continue

    fpath = matches[0]
    print(f"  File: {fpath.name}")

    with open(fpath, "rb") as f:
        data = pickle.load(f)

    journals = data.get("journals", [])

    # Filter for target investment
    filtered = [
        j for j in journals
        if getattr(j, "investment", None) == INVESTMENT
    ]

    print(f"  Total entries: {len(journals)}")
    print(f"  {INVESTMENT} entries: {len(filtered)}\n")

    if not filtered:
        continue

    # ── GROUP BY FINANCIAL ACCOUNT ────────────────────────────
    by_fa = defaultdict(list)
    for je in filtered:
        fa = getattr(je, "financial_account", "UNKNOWN")
        if fa in EXCLUDE_ACCOUNTS:
            continue
        by_fa[fa].append(je)

    # ── PRINT BY FA ───────────────────────────────────────────
    grand_qty   = 0.0
    grand_local = 0.0
    grand_book  = 0.0

    for fa in sorted(by_fa.keys()):
        entries = by_fa[fa]

        fa_qty   = 0.0
        fa_local = 0.0
        fa_book  = 0.0

        print(f"  {'─'*56}")
        print(f"  ACCOUNT: {fa}  ({len(entries)} entries)")
        print(f"  {'─'*56}")
        print(f"  {'DATE':<12} {'TRANSACTION':<20} {'QTY':>12} {'LOCAL':>14} {'BOOK':>14}")
        print(f"  {'─'*56}")

        for je in sorted(entries, key=lambda x: getattr(x, "ibor_date", None) or ""):
            ibor  = getattr(je, "ibor_date",        None)
            tran  = getattr(je, "transaction",       "")
            qty   = getattr(je, "quantity",          None) or 0.0
            local = getattr(je, "local",             None) or 0.0
            book  = getattr(je, "book",              None) or 0.0

            date_str = ibor.strftime("%Y-%m-%d") if ibor else "None"

            print(
                f"  {date_str:<12} {tran:<20} "
                f"{qty:>12,.4f} {local:>14,.4f} {book:>14,.4f}"
            )

            fa_qty   += qty
            fa_local += local
            fa_book  += book

        print(f"  {'─'*56}")
        print(
            f"  {'TOTAL ' + fa:<32} "
            f"{fa_qty:>12,.4f} {fa_local:>14,.4f} {fa_book:>14,.4f}"
        )
        print()

        grand_qty   += fa_qty
        grand_local += fa_local
        grand_book  += fa_book

    # ── GRAND TOTAL ───────────────────────────────────────────
    print(f"  {'='*56}")
    print(
        f"  {'GRAND TOTAL':<32} "
        f"{grand_qty:>12,.4f} {grand_local:>14,.4f} {grand_book:>14,.4f}"
    )
    print(f"  {'='*56}\n")

    # ── ALSO SHOW EXCLUDED ACCOUNTS SUMMARY ──────────────────
    excluded_by_fa = defaultdict(list)
    for je in filtered:
        fa = getattr(je, "financial_account", "UNKNOWN")
        if fa in EXCLUDE_ACCOUNTS:
            excluded_by_fa[fa].append(je)

    if excluded_by_fa:
        print(f"  EXCLUDED ACCOUNTS (stat only — not in totals):")
        for fa in sorted(excluded_by_fa.keys()):
            entries = excluded_by_fa[fa]
            total_book = sum(getattr(je, "book", None) or 0.0 for je in entries)
            print(f"    {fa:<30} entries={len(entries):>4}  total_book={total_book:>14,.4f}")
        print()