"""
compute_balance_sheet.py
──────────────────────────────────────────────────────────────────────────────
Registered compute function for the fig_code architecture.

Produces the complete balance sheet for any portfolio, calendar, and period
range. Opening balances, period movements, and closing balances — classified
by economic category and grouped by balance sheet section.

This is the accountant's view of the complete financial state.
Every other report is a subset of this output.

Architecture:
  - Reads from the same prep state as compute_accounting_ledger
  - Uses compute_classifications.py for account classification
  - Opening = prior state snapshot
  - Movement = journal entries for the period
  - Closing = current state snapshot
  - Opening + Movement = Closing is verified as an invariant

Balance sheet structure:
  Assets      — Cost, Receivables, Accrued Interest, Unrealized Gains
  Liabilities — Payables
  Revenue     — Income, Realized Price Gain, Realized FX Gain
  Expenses    — Expense accounts
  Capital     — Contributed Cost / capital flows

Drop into:
  financial_information_gateway/fig_code/compute_balance_sheet.py

Register in compute_registry.py:
  from financial_information_gateway.fig_code.compute_balance_sheet import compute_balance_sheet
  COMPUTE_REGISTRY["compute_balance_sheet"] = compute_balance_sheet
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_classifications import (
    ACCOUNT_CLASSIFICATION,
    BS_GROUP_ORDER,
    BS_SECTION_ORDER,
    Category,
    unknown_accounts,
    STAT_ONLY_ACCOUNTS,
)


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

TOLERANCE = 1e-6


# ──────────────────────────────────────────────────────────────────────────────
# STATE EXTRACTION
# ──────────────────────────────────────────────────────────────────────────────
def _extract_state_balances(state, uber_filter=None) -> dict:
    """
    Extract all account balances from a state snapshot.
    Returns dict keyed by (investment, financial_account) ->
    {quantity, local, book}.

    Reads from:
      - asset_liability_repository  -> investment_positions -> subspace.entries
      - revenue_expense_repository  -> balance_spaces_library -> balance_space["entries"]

    Excludes stat-only accounts.
    """
    balances = {}

    if not state:
        return balances

    def passes(inv):
        if not uber_filter:
            return True
        if "investment" in uber_filter:
            return inv == uber_filter["investment"]
        return True

    def decode(row):
        qty = row[0] if len(row) > 0 else 0.0
        local = row[1] if len(row) > 1 else 0.0
        book = row[2] if len(row) > 2 else 0.0
        return qty, local, book

    # ── ASSET / LIABILITY ─────────────────────────────────────────────
    al_repo = state["asset_liability_repository"]
    for subspace in al_repo.investment_positions.values():
        for key, row in subspace.entries.items():
            (_, inv, lotid, tax_date, ls, loc, fa) = key
            if fa in STAT_ONLY_ACCOUNTS:
                continue
            if not passes(inv):
                continue
            qty, local, book = decode(row)
            k = (inv, fa)
            if k not in balances:
                balances[k] = {"quantity": 0.0, "local": 0.0, "book": 0.0}
            balances[k]["quantity"] += qty
            balances[k]["local"] += local
            balances[k]["book"] += book

    # ── REVENUE / EXPENSE ─────────────────────────────────────────────
    # Balances stored in balance_spaces_library, NOT in .entries
    # .entries is the raw JE list — balance_spaces_library holds accumulated balances
    re_repo = state["revenue_expense_repository"]
    for investment, balance_space in re_repo.balance_spaces_library.items():
        if not passes(investment):
            continue
        for key, row in balance_space["entries"].items():
            if not isinstance(key, tuple) or len(key) < 7:
                continue
            (_, inv, lotid, tax_date, ls, loc, fa) = key
            if fa in STAT_ONLY_ACCOUNTS:
                continue
            qty, local, book = decode(row)
            k = (inv, fa)
            if k not in balances:
                balances[k] = {"quantity": 0.0, "local": 0.0, "book": 0.0}
            balances[k]["quantity"] += qty
            balances[k]["local"] += local
            balances[k]["book"] += book

    return balances

# ──────────────────────────────────────────────────────────────────────────────
# JOURNAL MOVEMENT EXTRACTION
# ──────────────────────────────────────────────────────────────────────────────

def _extract_movements(prep, uber_filter=None) -> dict:
    """
    Aggregate journal entry movements by (investment, financial_account).
    Returns dict keyed by (investment, financial_account) ->
    {local, book, quantity}.

    This is the movement column of the balance sheet —
    what happened during the period.
    Excludes stat-only accounts (MarketVal, offset accounts).
    """
    movements = {}

    prior_cutoff = prep["prior_cutoff_datetime"]
    current_cutoff = prep["current_cutoff_datetime"]

    for je in prep["journal_entries"]:

        inv = getattr(je, "investment", None)
        fa = getattr(je, "financial_account", None)

        if inv is None or fa is None:
            continue
        if fa in STAT_ONLY_ACCOUNTS:
            continue

        if uber_filter and "investment" in uber_filter:
            if inv != uber_filter["investment"]:
                continue

        is_adj = getattr(je, "is_adjustment", False)
        if not is_adj:
            ibor = getattr(je, "ibor_date", None)
            if not ibor:
                continue
            if not isinstance(ibor, datetime):
                try:
                    ibor = datetime.fromisoformat(str(ibor))
                except Exception:
                    continue
            if prior_cutoff is None:
                if ibor > current_cutoff:
                    continue
            else:

                if not (prior_cutoff < ibor <= current_cutoff):
                    continue

        k = (inv, fa)
        if k not in movements:
            movements[k] = {"quantity": 0.0, "local": 0.0, "book": 0.0}

        movements[k]["quantity"] += getattr(je, "quantity", 0.0) or 0.0
        movements[k]["local"] += getattr(je, "local", 0.0) or 0.0
        movements[k]["book"] += getattr(je, "book", 0.0) or 0.0

    return movements

# ──────────────────────────────────────────────────────────────────────────────
# BUILD BALANCE SHEET ROWS
# ──────────────────────────────────────────────────────────────────────────────

def _build_rows(opening_map, closing_map, movement_map) -> list[dict]:
    """
    Combine opening, movement, and closing into one row per
    (investment, financial_account).

    Verifies opening + movement ≈ closing for every row.
    Flags failures — does not suppress them.
    """
    all_keys = set(opening_map) | set(closing_map) | set(movement_map)

    rows = []
    failures = []

    for (inv, fa) in sorted(all_keys):
        o = opening_map.get( (inv, fa), {"quantity": 0.0, "local": 0.0, "book": 0.0})
        m = movement_map.get((inv, fa), {"quantity": 0.0, "local": 0.0, "book": 0.0})
        c = closing_map.get( (inv, fa), {"quantity": 0.0, "local": 0.0, "book": 0.0})

        # Invariant check: opening + movement = closing
        book_diff = abs((o["book"] + m["book"]) - c["book"])
        ties      = book_diff <= TOLERANCE

        if not ties:
            failures.append({
                "investment":        inv,
                "financial_account": fa,
                "book_diff":         book_diff,
            })

        category = ACCOUNT_CLASSIFICATION.get(fa, "Unknown")

        # Determine balance sheet section
        section = "Unknown"
        label   = fa
        for sec, cat, lbl in BS_GROUP_ORDER:
            if cat == category:
                section = sec
                label   = lbl
                break

        rows.append({
            "investment":        inv,
            "financial_account": fa,
            "category":          category,
            "section":           section,
            "section_label":     label,

            # Opening
            "open_qty":          o["quantity"],
            "open_local":        o["local"],
            "open_book":         o["book"],

            # Movement
            "move_qty":          m["quantity"],
            "move_local":        m["local"],
            "move_book":         m["book"],

            # Closing
            "close_qty":         c["quantity"],
            "close_local":       c["local"],
            "close_book":        c["book"],

            # Invariant
            "ties":              ties,
            "book_diff":         round(book_diff, 8),
        })

    return rows, failures


# ──────────────────────────────────────────────────────────────────────────────
# SECTION SUBTOTALS
# ──────────────────────────────────────────────────────────────────────────────

def _add_subtotals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append section subtotal rows and a grand total row.
    Subtotals sum open_book, move_book, close_book per section.
    """
    numeric_cols = [
        "open_qty",   "open_local",   "open_book",
        "move_qty",   "move_local",   "move_book",
        "close_qty",  "close_local",  "close_book",
    ]

    subtotal_rows = []

    for section in BS_SECTION_ORDER:
        section_df = df[df["section"] == section]
        if section_df.empty:
            continue

        subtotal = {col: section_df[col].sum() for col in numeric_cols}
        subtotal.update({
            "investment":        "__SUBTOTAL__",
            "financial_account": f"── {section} Total",
            "category":          "__subtotal__",
            "section":           section,
            "section_label":     f"{section} Total",
            "ties":              True,
            "book_diff":         0.0,
            "row_type":          "subtotal",
        })
        subtotal_rows.append(subtotal)

    # Grand total
    grand = {col: df[col].sum() for col in numeric_cols}
    grand.update({
        "investment":        "__TOTAL__",
        "financial_account": "── Grand Total",
        "category":          "__total__",
        "section":           "__total__",
        "section_label":     "Grand Total",
        "ties":              True,
        "book_diff":         0.0,
        "row_type":          "grand_total",
    })
    subtotal_rows.append(grand)

    df["row_type"] = "detail"

    subtotal_df = pd.DataFrame(subtotal_rows)
    result      = pd.concat([df, subtotal_df], ignore_index=True)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# MAIN COMPUTE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def compute_balance_sheet(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
    include_zero_rows: bool      = False,
    summary_only: bool           = False,
) -> ComputeResult:
    """
    Compute the complete balance sheet for a portfolio, calendar,
    and period range.

    Every account. Opening balances, period movements, closing balances.
    Classified by economic category. Grouped by balance sheet section.
    Invariant verified: opening + movement = closing for every row.

    Parameters
    ----------
    portfolio         : Portfolio name e.g. "Portfolio1"
    calendar          : Calendar name e.g. "Monthly"
    period_start      : Period start key e.g. "2021-01"
    period_end        : Period end key e.g. "2021-12"
    uber_filter       : Optional single-investment filter
    prep              : Pre-loaded prep dict from prep_state (required)
    include_zero_rows : Include rows where all values are zero (default False)
    summary_only      : Return subtotals and grand total only (default False)

    Returns
    -------
    ComputeResult with shape='balance_sheet'
    """

    t_total = time.perf_counter()

    if prep is None:
        raise ValueError(
            "prep is required. Call prep_state() and pass the result."
        )

    # ── EXTRACT OPENING AND CLOSING FROM STATE SNAPSHOTS ─────────────
    t_extract = time.perf_counter()

    opening_map = _extract_state_balances(
        prep["prior_state"],
        uber_filter
    )
    closing_map = _extract_state_balances(
        prep["current_state"],
        uber_filter
    )

    t_extract_ms = (time.perf_counter() - t_extract) * 1000

    # ── EXTRACT MOVEMENTS FROM JOURNAL ENTRIES ────────────────────────
    t_move = time.perf_counter()

    movement_map = _extract_movements(prep, uber_filter)

    t_move_ms = (time.perf_counter() - t_move) * 1000

    # ── BUILD ROWS ────────────────────────────────────────────────────
    t_build = time.perf_counter()

    rows, failures = _build_rows(opening_map, closing_map, movement_map)

    if not rows:
        return ComputeResult(
            function="compute_balance_sheet",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="balance_sheet",
            data=pd.DataFrame(),
            valid=False,
            errors=["No balance sheet rows produced"],
            metadata={},
        )

    df = pd.DataFrame(rows)

    # Flag unknown accounts
    unk = [r for r in rows if r["category"] == "Unknown"]
    if unk:
        unknown = list({r["financial_account"] for r in unk})
        print(f"⚠️  Unknown accounts (not in classification): {unknown}")

    # ── FILTER ZERO ROWS ──────────────────────────────────────────────
    if not include_zero_rows:
        df = df[
            (df["open_book"].abs()  > TOLERANCE) |
            (df["move_book"].abs()  > TOLERANCE) |
            (df["close_book"].abs() > TOLERANCE)
        ].copy()

    # ── SORT by section order then investment ─────────────────────────
    section_order_map = {s: i for i, s in enumerate(BS_SECTION_ORDER)}
    df["section_order"] = df["section"].map(
        lambda s: section_order_map.get(s, 99)
    )
    event_order = {"OPENING": 0, "ACTIVITY": 1, "CLOSING": 2}
    df["event_order"] = df["event_type"].map(event_order).fillna(1)
    df = df.sort_values(
        by=["investment", "event_order", "ibor_date", "sequence"]
    ).drop(columns=["event_order"]).reset_index(drop=True)

    # ── ADD SUBTOTALS ─────────────────────────────────────────────────
    df = _add_subtotals(df)

    # ── SUMMARY ONLY ──────────────────────────────────────────────────
    if summary_only:
        df = df[df["row_type"].isin(["subtotal", "grand_total"])].copy()

    t_build_ms = (time.perf_counter() - t_build) * 1000

    # ── METADATA ──────────────────────────────────────────────────────
    t_total_ms = (time.perf_counter() - t_total) * 1000

    n_investments = df[
        df["row_type"] == "detail"
    ]["investment"].nunique() if "row_type" in df.columns else 0

    n_failures = len(failures)
    valid      = n_failures == 0

    if failures:
        print(f">>> BALANCE SHEET INVARIANT FAILURES: {n_failures}")
        for f in failures[:5]:
            print(
                f"    {f['investment']} | {f['financial_account']} "
                f"| diff={f['book_diff']:.8f}"
            )
        if n_failures > 5:
            print(f"    ... and {n_failures - 5} more")

    metadata = {
        "elapsed_ms":      round(t_total_ms, 1),
        "extract_ms":      round(t_extract_ms, 1),
        "movement_ms":     round(t_move_ms, 1),
        "build_ms":        round(t_build_ms, 1),
        "investments":     n_investments,
        "detail_rows":     len(df[df.get("row_type", "detail") == "detail"])
                           if "row_type" in df.columns else len(df),
        "invariant_failures": n_failures,
        "unknown_accounts":   list({r["financial_account"]
                                    for r in rows
                                    if r["category"] == "Unknown"}),
        "uber_filter":     uber_filter,
    }

    print(
        f">>> compute_balance_sheet COMPLETE "
        f"| {portfolio} | {calendar} "
        f"| {period_start} → {period_end} "
        f"| {n_investments} investments "
        f"| {n_failures} invariant failures "
        f"| {t_total_ms:.0f}ms"
    )

    return ComputeResult(
        function="compute_balance_sheet",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="balance_sheet",
        data=df,
        valid=valid,
        errors=[
            f"{f['investment']}|{f['financial_account']}|diff={f['book_diff']:.8f}"
            for f in failures
        ],
        metadata=metadata,
    )