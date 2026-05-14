"""
compute_capital.py
──────────────────────────────────────────────────────────────────────────────
Computes capital flows for any portfolio, calendar, and period.

Sources (from compute_classifications.py):
  CAPITAL_ACCOUNTS — ContributedCost

Capital flows are external cash movements into or out of the portfolio —
contributions and withdrawals. These are the same journal entries that
feed the TWR cash flow denominator and the balance sheet capital section.

This is the cleanest recon check:
  Opening NAV + Capital Flows + Income + Realized Gains + Unrealized Change
  = Closing NAV

Every term in that equation is a compute function. The recon endpoint
will prove they all add up.

Output shapes:
  detail   — one row per capital flow event
  summary  — one row per investment, net flow for the period
  total    — portfolio total capital flow

Drop into:
  financial_information_gateway/fig_code/compute_capital.py

Register in compute_registry.py:
  COMPUTE_REGISTRY["compute_capital"] = compute_capital
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_classifications import (
    CAPITAL_ACCOUNTS,
    ACCOUNT_CLASSIFICATION,
)

TOLERANCE = 1e-6


# ──────────────────────────────────────────────────────────────────────────────
# EXTRACTION
# ──────────────────────────────────────────────────────────────────────────────

def _extract_capital(prep, uber_filter=None) -> pd.DataFrame:
    """
    Extract all capital flow journal entries for the period.
    ContributedCost entries — positive = contribution, negative = withdrawal.
    """
    prior_cutoff   = prep["prior_cutoff_datetime"]
    current_cutoff = prep["current_cutoff_datetime"]

    rows = []

    for je in prep["journal_entries"]:
        fa  = getattr(je, "financial_account", None)
        inv = getattr(je, "investment", None)

        if fa not in CAPITAL_ACCOUNTS:
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

        rows.append({
            "investment":        inv,
            "lotid":             getattr(je, "lotid",       None),
            "ibor_date":         getattr(je, "ibor_date",   None),
            "trade_date":        getattr(je, "tradedate",   None),
            "settle_date":       getattr(je, "settledate",  None),
            "transaction":       getattr(je, "transaction", None),
            "tranid":            getattr(je, "tranid",      None),
            "financial_account": fa,
            "quantity":          getattr(je, "quantity",    0.0),
            "local":             getattr(je, "local",       0.0),
            "book":              getattr(je, "book",        0.0),
            "flow_type":         "Contribution" if getattr(je, "book", 0.0) > 0
                                 else "Withdrawal",
            "is_adjustment":     is_adj,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# SHAPE — SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

def _shape_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Net capital flow per investment for the period."""
    if df.empty:
        return pd.DataFrame()

    summary = (
        df.groupby("investment")[["quantity", "local", "book"]]
        .sum()
        .reset_index()
        .rename(columns={
            "quantity": "net_shares",
            "local":    "net_local",
            "book":     "net_book",
        })
    )

    summary["flow_type"] = summary["net_book"].apply(
        lambda x: "Net Contribution" if x > 0
        else "Net Withdrawal" if x < 0
        else "Flat"
    )

    # Grand total
    grand = pd.DataFrame([{
        "investment": "── TOTAL",
        "net_shares": summary["net_shares"].sum(),
        "net_local":  summary["net_local"].sum(),
        "net_book":   summary["net_book"].sum(),
        "flow_type":  "── Grand Total",
    }])

    return pd.concat(
        [summary.sort_values("investment"), grand],
        ignore_index=True
    )


# ──────────────────────────────────────────────────────────────────────────────
# SUBTOTALS FOR DETAIL
# ──────────────────────────────────────────────────────────────────────────────

def _add_subtotals(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-investment subtotals and grand total to detail output."""
    if df.empty:
        return df

    numeric_cols = [c for c in ["quantity", "local", "book"] if c in df.columns]
    subtotal_rows = []

    for inv, group in df.groupby("investment"):
        sub = {col: group[col].sum() for col in numeric_cols}
        sub.update({
            "investment":        inv,
            "lotid":             None,
            "ibor_date":         None,
            "trade_date":        None,
            "settle_date":       None,
            "transaction":       "── Subtotal",
            "tranid":            None,
            "financial_account": None,
            "flow_type":         "── Subtotal",
            "row_type":          "subtotal",
        })
        subtotal_rows.append(sub)

    grand = {col: df[col].sum() for col in numeric_cols}
    grand.update({
        "investment":        "── TOTAL",
        "lotid":             None,
        "ibor_date":         None,
        "trade_date":        None,
        "settle_date":       None,
        "transaction":       "── Grand Total",
        "tranid":            None,
        "financial_account": None,
        "flow_type":         "── Grand Total",
        "row_type":          "grand_total",
    })
    subtotal_rows.append(grand)

    df["row_type"] = "detail"
    return pd.concat(
        [df, pd.DataFrame(subtotal_rows)], ignore_index=True
    )


# ──────────────────────────────────────────────────────────────────────────────
# MAIN COMPUTE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def compute_capital(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
    shape:        str            = "summary",  # "detail", "summary"
) -> ComputeResult:
    """
    Compute capital flows for a portfolio, calendar, and period range.

    Capital flows are the external cash movements that form the
    denominator of the TWR calculation. These are the ContributedCost
    journal entries — the same entries that feed the balance sheet
    capital section and the performance cash flow components.

    shape parameter:
      "detail"  — one row per capital flow event
      "summary" — one row per investment, net flow (default)

    The grand total capital flow for the period is the number that,
    combined with opening NAV, income, realized gains, and unrealized
    change, must equal closing NAV. The recon endpoint proves this.
    """

    t_total = time.perf_counter()

    if prep is None:
        raise ValueError("prep is required.")

    if shape not in ("detail", "summary"):
        raise ValueError(
            f"Invalid shape '{shape}'. Use 'detail' or 'summary'."
        )

    # Extract
    t_extract = time.perf_counter()
    raw_df = _extract_capital(prep, uber_filter)
    t_extract_ms = (time.perf_counter() - t_extract) * 1000

    if raw_df.empty:
        return ComputeResult(
            function="compute_capital",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="capital",
            data=pd.DataFrame(),
            valid=True,
            errors=[],
            metadata={"note": "No capital flows in this period"},
        )

    # Shape
    t_shape = time.perf_counter()

    if shape == "detail":
        output_df = _add_subtotals(
            raw_df.sort_values(["investment", "ibor_date"]).reset_index(drop=True)
        )
    else:
        output_df = _shape_summary(raw_df)

    t_shape_ms  = (time.perf_counter() - t_shape) * 1000
    t_total_ms  = (time.perf_counter() - t_total) * 1000

    n_investments  = raw_df["investment"].nunique()
    n_flows        = len(raw_df)
    net_book       = raw_df["book"].sum()

    print(
        f">>> compute_capital COMPLETE "
        f"| {portfolio} | {calendar} "
        f"| {period_start} → {period_end} "
        f"| {n_investments} investments "
        f"| {n_flows} flow events "
        f"| net_book={net_book:,.2f} "
        f"| {t_total_ms:.0f}ms"
    )

    metadata = {
        "elapsed_ms":    round(t_total_ms, 1),
        "extract_ms":    round(t_extract_ms, 1),
        "shape_ms":      round(t_shape_ms, 1),
        "investments":   n_investments,
        "flow_events":   n_flows,
        "net_book":      round(net_book, 2),
        "shape":         shape,
        "uber_filter":   uber_filter,
    }

    return ComputeResult(
        function="compute_capital",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="capital",
        data=output_df,
        valid=True,
        errors=[],
        metadata=metadata,
    )
