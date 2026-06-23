# ============================================================
# Visibility — Compute Accounting Ledger
# compute_accounting_ledger.py
#
# The foundational compute function.
# Produces the complete, consistent financial state for any
# portfolio, calendar, and period range.
#
# This is the supermarket — every account, every lot, every
# movement, every journal entry. Filters, groupings, and
# report shapes are applied on top of this output.
#
# All prepared reports and user-defined reports consume
# this function's output. It is the single source of truth
# for all financial reporting in Visibility.
# ============================================================

import pandas as pd
from datetime import datetime

# At top of file — change import
from financial_information_gateway.fig_code.fig_core import (
    prep_state_cached as prep_state,
    render
)

from financial_information_gateway.fig_code.compute_result import ComputeResult


# ============================================================
# CONSTANTS
# ============================================================

TOLERANCE = 1e-6


UNREALIZED_ACCOUNTS = {
    "UnrealizedGainLoss",
    "UnrealizedFX",
    "UnrealizedGainLossLocal",
    "UnrealizedFXLocal",
}

# ============================================================
# EXTRACT STRUCTURAL
# ============================================================

def _extract_structural(state, uber_filter=None):
    """
    Extract position rows from a state snapshot.
    Reads from asset_liability_repository and
    revenue_expense_repository.
    Returns a list of dicts — one per position key.
    """
    rows = []

    if not state:
        return rows

    al_repo = state["asset_liability_repository"]
    re_repo = state["revenue_expense_repository"]

    def passes(inv):
        if not uber_filter:
            return True
        if "investment" in uber_filter:
            return inv == uber_filter["investment"]
        return True

    def decode(row):
        qty   = row[0] if len(row) > 0 else 0.0
        local = row[1] if len(row) > 1 else 0.0
        book  = row[2] if len(row) > 2 else 0.0
        return qty, local, book

    # --------------------------------------------------
    # ASSET / LIABILITY
    # --------------------------------------------------
    for subspace in al_repo.investment_positions.values():
        for key, row in subspace.entries.items():

            (_, inv, lotid, tax_date, ls, loc, fa) = key

            if not passes(inv):
                continue

            qty, local, book = decode(row)

            rows.append({
                "investment":       inv,
                "lotid":            lotid,
                "tax_date":         tax_date,
                "location":         loc,
                "ls":               ls,
                "financial_account": fa,
                "quantity":         qty,
                "local":            local,
                "book":             book,
            })

    # REVENUE / EXPENSE — read from balance_spaces_library
    for inv, bs in re_repo.balance_spaces_library.items():
        if not passes(inv):
            continue
        for key, row in bs["entries"].items():
            if not isinstance(key, tuple) or len(key) < 7:
                continue
            (_, inv2, lotid, tax_date, ls, loc, fa) = key
            qty, local, book = decode(row)
            rows.append({
                "investment": inv2,
                "lotid": lotid,
                "tax_date": tax_date,
                "location": loc,
                "ls": ls,
                "financial_account": fa,
                "quantity": qty,
                "local": local,
                "book": book,
            })

    return rows

# ============================================================
# MATERIALIZE
# ============================================================


def _materialize(prep, uber_filter=None, ppa_ibor_date=None):
    """
    Bridge between state snapshots and journal entries.

    Opening and closing balances come from state dicts.
    Journal entries are Python objects accessed via getattr.

    This dual access pattern is intentional and critical —
    state is optimized for fast keyed lookup,
    journals carry full event context as objects.

    Adjusting entries are identified by is_adjustment flag
    set at load time in prep_state — not by a field on the
    object itself.

    PPA IBOR date is assigned by the caller. Default is the
    first moment of the current period. The original trade
    IBOR date is never used — that would insert activity
    into a closed period and produce incorrect books.

    Returns a balances dict keyed by the six-tuple
    (investment, lotid, tax_date, location, ls, financial_account)
    """

    from datetime import timedelta

    prior_cutoff = prep["prior_cutoff_datetime"]
    current_cutoff = prep["current_cutoff_datetime"]

    # Resolve PPA IBOR date — default to first moment of period
    effective_ppa_ibor = ppa_ibor_date or (
        prior_cutoff + timedelta(seconds=1)
        if prior_cutoff else current_cutoff
    )

    prior_rows = _extract_structural(prep["prior_state"], uber_filter)
    current_rows = _extract_structural(prep["current_state"], uber_filter)

    opening_map = {}
    closing_map = {}

    for r in prior_rows:
        key = (
            r["investment"],
            r["lotid"],
            r["tax_date"],
            r["location"],
            r["ls"],
            r["financial_account"],
        )
        opening_map[key] = r

    for r in current_rows:
        key = (
            r["investment"],
            r["lotid"],
            r["tax_date"],
            r["location"],
            r["ls"],
            r["financial_account"],
        )
        closing_map[key] = r


    keys = set(opening_map) | set(closing_map)

    # ── TEMP DEBUG ──────────────────────────────────────────
    print(f">>> DEBUG opening_map={len(opening_map)} closing_map={len(closing_map)} keys={len(keys)}")
    # ── END DEBUG ───────────────────────────────────────────

    balances = {}

    # --------------------------------------------------
    # STATE → OPEN / MOVEMENT / CLOSE
    # Dict access throughout — state snapshots are dicts
    # --------------------------------------------------
    for k in keys:
        o = opening_map.get(k, {"quantity": 0.0, "local": 0.0, "book": 0.0})
        c = closing_map.get(k, {"quantity": 0.0, "local": 0.0, "book": 0.0})

        balances[k] = {
            "opening_qty": o.get("quantity", 0.0),
            "opening_local": o.get("local", 0.0),
            "opening_book": o.get("book", 0.0),

            "movement_qty": c.get("quantity", 0.0) - o.get("quantity", 0.0),
            "movement_local": c.get("local", 0.0) - o.get("local", 0.0),
            "movement_book": c.get("book", 0.0) - o.get("book", 0.0),

            "closing_qty": c.get("quantity", 0.0),
            "closing_local": c.get("local", 0.0),
            "closing_book": c.get("book", 0.0),

            "je_lines": []
        }

    # --------------------------------------------------
    # ATTACH JOURNALS
    # Object access throughout — journal entries are objects
    #
    # ADJUSTMENT IDENTIFICATION:
    # is_adjustment is set at load time in prep_state.
    # It is not a native field on the journal object.
    # We set it ourselves when loading the adjusting file.
    #
    # IBOR DATE ASSIGNMENT:
    # Regular entries  → use their own ibor_date
    # Adjusting entries → use effective_ppa_ibor
    #   (original trade ibor_date is wrong for adjusting
    #    entries — it references a closed period)
    # --------------------------------------------------
    for je in prep["journal_entries"]:

        # Filter by investment if requested
        if uber_filter:
            if getattr(je, "investment", None) != uber_filter.get("investment"):
                continue

        # Identify adjustment — flag set at load time
        is_adjustment = getattr(je, "is_adjustment", False)

        # Assign IBOR date
        if is_adjustment:
            je_ibor = effective_ppa_ibor
        else:
            je_ibor = getattr(je, "ibor_date", None)
            if not je_ibor:
                continue
            if prior_cutoff is None:
                if je_ibor > current_cutoff:
                    continue
            else:
                if prior_cutoff is None:
                    if je_ibor > current_cutoff:
                        continue
                else:
                    if not (prior_cutoff < je_ibor <= current_cutoff):
                        continue

        # Build exact key — no fuzzy matching
        je_key = (
            getattr(je, "investment", None),
            getattr(je, "lotid", None),
            getattr(je, "tax_date", None),
            getattr(je, "location", None),
            getattr(je, "ls", None),
            getattr(je, "financial_account", None),
        )

        if je_key not in balances:
            continue

        # Append journal line
        # Note: sequence_number not sequence — confirmed from
        # raw object inspection
        balances[je_key]["je_lines"].append({
            "ibor_date": je_ibor,
            "trade_date": getattr(je, "tradedate", None),
            "settle_date": getattr(je, "settledate", None),
            "sequence": getattr(je, "sequence_number", 0),
            "qty": getattr(je, "quantity", 0.0),
            "local": getattr(je, "local", 0.0),
            "book": getattr(je, "book", 0.0),
            "transaction": getattr(je, "transaction", None),
            "lotid": getattr(je, "lotid", None),
            "tax_date": getattr(je, "tax_date", None),
            "tranid": getattr(je, "tranid", None),
            "is_ppa": is_adjustment,
        })

    # Sort journal lines into chronological order
    for b in balances.values():
        b["je_lines"].sort(key=lambda x: (
            x["ibor_date"] or datetime.min,
            x["sequence"]
        ))

    return balances

# ============================================================
# VALIDATE INVARIANTS
# ============================================================

def _validate(balances):
    """
    Verify opening + movement == closing for every position.
    Returns list of failing keys — empty list means clean.
    """
    failures = []

    for key, b in balances.items():
        if abs((b["opening_qty"] + b["movement_qty"])
               - b["closing_qty"]) > TOLERANCE:
            failures.append(key)

    return failures


# ============================================================
# RENDER TO DATAFRAME
# ============================================================

def _to_dataframe(balances, prior_cutoff, current_cutoff):
    """
    Convert materialized balances to a DataFrame.

    Emits three row types per position:
        OPENING  — synthetic row at prior_cutoff
        ACTIVITY — one row per journal entry
        CLOSING  — synthetic row at current_cutoff

    This structure is the complete audit trail.
    Every report derives from this output.
    """
    rows = []

    for (inv, lotid, tax_date, loc, ls, fa), b in balances.items():

        # OPENING
        rows.append({
            "ibor_date":         prior_cutoff,
            "event_type":        "OPENING",
            "investment":        inv,
            "lotid":             lotid,
            "tax_date":          tax_date,
            "location":          loc,
            "ls":                ls,
            "financial_account": fa,
            "qty":               b["opening_qty"],
            "local":             b["opening_local"],
            "book":              b["opening_book"],
            "transaction":       None,
            "tranid":            None,
            "sequence":          -1,
            "is_ppa":            False,
        })

        # ACTIVITY
        for je in b["je_lines"]:
            rows.append({
                "ibor_date":         je["ibor_date"],
                "event_type":        "ACTIVITY",
                "investment":        inv,
                "lotid":             je["lotid"],
                "tax_date":          je["tax_date"],
                "location":          loc,
                "ls":                ls,
                "financial_account": fa,
                "qty":               je["qty"],
                "local":             je["local"],
                "book":              je["book"],
                "transaction":       je["transaction"],
                "tranid":            je["tranid"],
                "sequence":          je["sequence"],
                "is_ppa":            je["is_ppa"],
            })

        # CLOSING
        rows.append({
            "ibor_date":         current_cutoff,
            "event_type":        "CLOSING",
            "investment":        inv,
            "lotid":             lotid,
            "tax_date":          tax_date,
            "location":          loc,
            "ls":                ls,
            "financial_account": fa,
            "qty":               b["closing_qty"],
            "local":             b["closing_local"],
            "book":              b["closing_book"],
            "transaction":       None,
            "tranid":            None,
            "sequence":          999999,
            "is_ppa":            False,
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df["ibor_date"] = pd.to_datetime(df["ibor_date"], errors="coerce")

    event_order = {"OPENING": 0, "ACTIVITY": 1, "CLOSING": 2}
    df["event_order"] = df["event_type"].map(event_order).fillna(1)
    df = df.sort_values(
        by=["investment", "event_order", "ibor_date", "sequence"]
    ).drop(columns=["event_order"]).reset_index(drop=True)

    return df


def _assign_ppa_ibor_date(je, prep, mode="period_start"):
    """
    Assign IBOR date to a prior period adjustment journal entry.

    mode='period_start'   — first moment of adjustment period
                            (prior_cutoff + 1 second)
    mode='adjustment_date' — actual date correction was made
                             (kdbegin of the adjusting event)
    """
    if mode == "period_start":
        from datetime import timedelta
        return prep["prior_cutoff_datetime"] + timedelta(seconds=1)

    elif mode == "adjustment_date":
        return getattr(je, "kdbegin", None)

    else:
        raise ValueError(f"Unknown PPA date mode: {mode}")

# ============================================================
# COMPUTE ACCOUNTING LEDGER — PUBLIC INTERFACE
# ============================================================
def compute_accounting_ledger(
        portfolio,
        calendar,
        period_start,
        period_end,
        uber_filter=None,
        prep=None,
        ppa_ibor_date=None
):


    """
    The foundational compute function for Visibility.

    Produces the complete financial state for a portfolio,
    calendar, and period range as a structured DataFrame.

    Parameters
    ----------
    portfolio     : str   — portfolio identifier
    calendar      : str   — calendar name
    period_start  : str   — period start in YYYY-MM format
    period_end    : str   — period end in YYYY-MM format
    uber_filter   : dict  — optional e.g. {"investment": "ZTS"}
    prep          : dict  — optional pre-loaded prep package.
                           Pass this when calling multiple compute
                           functions against the same period to
                           avoid reloading state.
    ppa_ibor_date : datetime — IBOR date to assign to prior period
                           adjustment entries. Defaults to first
                           moment of the current period.
                           The original trade IBOR date must never
                           be used — it references a closed period.

    Returns
    -------
    ComputeResult with shape='accounting_ledger'

    Usage
    -----
    # Basic call
    result = compute_accounting_ledger(
        portfolio='Portfolio1',
        calendar='Monthly',
        period_start='2021-01',
        period_end='2021-12'
    )

    # With investment filter
    result = compute_accounting_ledger(
        portfolio='Portfolio1',
        calendar='Monthly',
        period_start='2021-01',
        period_end='2021-12',
        uber_filter={'investment': 'ZTS'}
    )

    # With explicit PPA IBOR date
    from datetime import datetime
    result = compute_accounting_ledger(
        portfolio='Portfolio1',
        calendar='Monthly',
        period_start='2021-12',
        period_end='2021-12',
        ppa_ibor_date=datetime(2021, 12, 1, 0, 0, 0)
    )

    # Reusing a prep package across multiple compute calls
    prep = prep_state('Portfolio1', 'Monthly', '2021-01', '2021-12')
    result = compute_accounting_ledger(..., prep=prep)
    """

    start_time = datetime.now()

    # --------------------------------------------------
    # PREP — load state and journals
    # Accept pre-loaded prep to avoid redundant IO
    # --------------------------------------------------
    if prep is None:
        prep = prep_state(portfolio, calendar, period_start, period_end)

    # --------------------------------------------------
    # MATERIALIZE — bridge state dicts and journal objects
    # --------------------------------------------------
    balances = _materialize(prep, uber_filter, ppa_ibor_date)

    # --------------------------------------------------
    # VALIDATE — invariant check
    # --------------------------------------------------
    failures = _validate(balances)
    valid = len(failures) == 0

    if failures:
        print(f">>> INVARIANT FAILURES: {len(failures)} keys failed")
        for f in failures[:5]:
            print(f"    {f}")
        if len(failures) > 5:
            print(f"    ... and {len(failures) - 5} more")

    # --------------------------------------------------
    # RENDER TO DATAFRAME
    # --------------------------------------------------
    df = _to_dataframe(
        balances,
        prep["prior_cutoff_datetime"],
        prep["current_cutoff_datetime"]
    )

    # --------------------------------------------------
    # METADATA
    # --------------------------------------------------
    elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

    adj_count = sum(
        1 for j in prep["journal_entries"]
        if getattr(j, "is_adjustment", False)
    )

    metadata = {
        "row_count": len(df),
        "position_count": len(balances),
        "journal_count": sum(
            len(b["je_lines"])
            for b in balances.values()
        ),
        "adjusting_count": adj_count,
        "invariant_failures": len(failures),
        "elapsed_ms": round(elapsed_ms, 2),
        "uber_filter": uber_filter,
        "ppa_ibor_date": str(ppa_ibor_date) if ppa_ibor_date else "default",
    }

    print(
        f">>> COMPUTE ACCOUNTING LEDGER COMPLETE "
        f"| {portfolio} | {calendar} "
        f"| {period_start} → {period_end} "
        f"| {metadata['row_count']} rows "
        f"| {metadata['adjusting_count']} adjusting "
        f"| {metadata['elapsed_ms']}ms"
    )

    return ComputeResult(
        function="compute_accounting_ledger",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="accounting_ledger",
        data=df,
        valid=valid,
        errors=[str(f) for f in failures],
        metadata=metadata,
    )

