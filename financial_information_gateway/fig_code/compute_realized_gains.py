"""
compute_realized_gains.py
──────────────────────────────────────────────────────────────────────────────
Computes realized gains and losses for any portfolio, calendar, and period.

Sources:
  PriceGainInvestment — realized price gain on disposed lots
  FXGainInvestment    — realized FX gain on disposed lots

These are revenue/expense account movements — the same journals that feed
the balance sheet, performance TWR, and the recon endpoint.

Output:
  One row per investment per disposition event showing:
    - Realized price gain (local and book)
    - Realized FX gain (book)
    - Total realized gain (book)
    - Trade date and IBOR date of disposition

Drop into:
  financial_information_gateway/fig_code/compute_realized_gains.py

Register in compute_registry.py:
  COMPUTE_REGISTRY["compute_realized_gains"] = compute_realized_gains
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_classifications import (
    REALIZED_ACCOUNTS,
    Category,
    ACCOUNT_CLASSIFICATION,
)

TOLERANCE = 1e-6


# ──────────────────────────────────────────────────────────────────────────────
# EXTRACTION
# ──────────────────────────────────────────────────────────────────────────────

def _extract_realized(prep, uber_filter=None) -> pd.DataFrame:
    """
    Extract all realized gain journal entries for the period.
    Returns raw rows — one per journal entry on a realized account.
    """
    prior_cutoff   = prep["prior_cutoff_datetime"]
    current_cutoff = prep["current_cutoff_datetime"]

    rows = []

    for je in prep["journal_entries"]:
        fa  = getattr(je, "financial_account", None)
        inv = getattr(je, "investment", None)

        if fa not in REALIZED_ACCOUNTS:
            continue

        if uber_filter and "investment" in uber_filter:
            if inv != uber_filter["investment"]:
                continue

        is_adj = getattr(je, "is_adjustment", False)
        if not is_adj:
            ibor = getattr(je, "ibor_date", None)
            if not ibor:
                continue
            if prior_cutoff is None:
                # First period — include all entries up to current_cutoff
                if ibor > current_cutoff:
                    continue
            else:
                if not (prior_cutoff < ibor <= current_cutoff):
                    continue

        category = ACCOUNT_CLASSIFICATION.get(fa, "Unknown")

        rows.append({
            "investment":        inv,
            "lotid":             getattr(je, "lotid",       None),
            "tax_date":          getattr(je, "tax_date",    None),
            "ibor_date":         getattr(je, "ibor_date",   None),
            "trade_date":        getattr(je, "tradedate",   None),
            "settle_date":       getattr(je, "settledate",  None),
            "transaction":       getattr(je, "transaction", None),
            "tranid":            getattr(je, "tranid",      None),
            "financial_account": fa,
            "category":          category,
            "local":             getattr(je, "local",       0.0),
            "book":              getattr(je, "book",        0.0),
            "is_adjustment":     is_adj,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# SHAPE OUTPUT
# ──────────────────────────────────────────────────────────────────────────────

def _shape_realized(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot raw realized entries into a clean gain/loss report.

    One row per (investment, lotid, tax_date, ibor_date, tranid) showing:
      realized_price_local, realized_price_book,
      realized_fx_book,
      realized_total_book
    """
    if df.empty:
        return pd.DataFrame()

    price_df = (
        df[df["category"] == Category.REALIZED_PRICE]
        .groupby(
            ["investment", "lotid", "tax_date", "ibor_date",
             "trade_date", "settle_date", "transaction", "tranid"],
            dropna=False
        )[["local", "book"]]
        .sum()
        .rename(columns={
            "local": "realized_price_local",
            "book":  "realized_price_book",
        })
        .reset_index()
    )

    fx_df = (
        df[df["category"] == Category.REALIZED_FX]
        .groupby(
            ["investment", "lotid", "tax_date", "ibor_date",
             "trade_date", "settle_date", "transaction", "tranid"],
            dropna=False
        )[["book"]]
        .sum()
        .rename(columns={"book": "realized_fx_book"})
        .reset_index()
    )

    key_cols = [
        "investment", "lotid", "tax_date", "ibor_date",
        "trade_date", "settle_date", "transaction", "tranid"
    ]

    if price_df.empty and fx_df.empty:
        return pd.DataFrame()
    elif price_df.empty:
        result = fx_df.copy()
        result["realized_price_local"] = 0.0
        result["realized_price_book"]  = 0.0
    elif fx_df.empty:
        result = price_df.copy()
        result["realized_fx_book"] = 0.0
    else:
        result = price_df.merge(fx_df, on=key_cols, how="outer").fillna(0.0)

    result["realized_total_book"] = (
        result["realized_price_book"] + result["realized_fx_book"]
    )

    result = result.sort_values(
        ["investment", "ibor_date", "lotid"]
    ).reset_index(drop=True)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# SUBTOTALS
# ──────────────────────────────────────────────────────────────────────────────

def _add_subtotals(df: pd.DataFrame) -> pd.DataFrame:
    """Add investment subtotals and grand total."""
    if df.empty:
        return df

    numeric_cols = [
        "realized_price_local", "realized_price_book",
        "realized_fx_book",     "realized_total_book",
    ]

    subtotal_rows = []

    for inv, group in df.groupby("investment"):
        sub = {col: group[col].sum() for col in numeric_cols}
        sub.update({
            "investment":  inv,
            "lotid":       None,
            "tax_date":    None,
            "ibor_date":   None,
            "trade_date":  None,
            "settle_date": None,
            "transaction": "── Subtotal",
            "tranid":      None,
            "row_type":    "subtotal",
        })
        subtotal_rows.append(sub)

    grand = {col: df[col].sum() for col in numeric_cols}
    grand.update({
        "investment":  "── TOTAL",
        "lotid":       None,
        "tax_date":    None,
        "ibor_date":   None,
        "trade_date":  None,
        "settle_date": None,
        "transaction": "── Grand Total",
        "tranid":      None,
        "row_type":    "grand_total",
    })
    subtotal_rows.append(grand)

    df["row_type"] = "detail"
    return pd.concat(
        [df, pd.DataFrame(subtotal_rows)], ignore_index=True
    )


# ──────────────────────────────────────────────────────────────────────────────
# MAIN COMPUTE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def compute_realized_gains(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
    summary_only: bool           = False,
) -> ComputeResult:
    """
    Compute realized gains and losses for a portfolio, calendar,
    and period range.

    Returns one row per disposition event — the lot-level gain/loss
    showing price gain and FX gain separately.

    These entries are the same journal entries that feed the balance
    sheet revenue section and the performance TWR. There is nothing
    to reconcile — it is the same data viewed as a gain/loss report.
    """

    t_total = time.perf_counter()

    if prep is None:
        raise ValueError("prep is required.")

    # Extract
    t_extract = time.perf_counter()
    raw_df = _extract_realized(prep, uber_filter)
    t_extract_ms = (time.perf_counter() - t_extract) * 1000

    if raw_df.empty:
        return ComputeResult(
            function="compute_realized_gains",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="realized_gains",
            data=pd.DataFrame(),
            valid=True,
            errors=[],
            metadata={"note": "No realized gains in this period"},
        )

    # Shape
    t_shape = time.perf_counter()
    df = _shape_realized(raw_df)
    t_shape_ms = (time.perf_counter() - t_shape) * 1000

    # Add subtotals
    df = _add_subtotals(df)

    if summary_only:
        df = df[df["row_type"].isin(["subtotal", "grand_total"])].copy()

    t_total_ms = (time.perf_counter() - t_total) * 1000

    n_investments = (
        df[df["row_type"] == "detail"]["investment"].nunique()
        if "row_type" in df.columns else df["investment"].nunique()
    )
    n_lots = len(
        df[df["row_type"] == "detail"]
        if "row_type" in df.columns else df
    )

    print(
        f">>> compute_realized_gains COMPLETE "
        f"| {portfolio} | {calendar} "
        f"| {period_start} → {period_end} "
        f"| {n_investments} investments "
        f"| {n_lots} disposition events "
        f"| {t_total_ms:.0f}ms"
    )

    metadata = {
        "elapsed_ms":   round(t_total_ms, 1),
        "extract_ms":   round(t_extract_ms, 1),
        "shape_ms":     round(t_shape_ms, 1),
        "investments":  n_investments,
        "detail_rows":  n_lots,
        "uber_filter":  uber_filter,
    }

    return ComputeResult(
        function="compute_realized_gains",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="realized_gains",
        data=df,
        valid=True,
        errors=[],
        metadata=metadata,
    )
