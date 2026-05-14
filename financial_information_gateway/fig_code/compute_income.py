"""
compute_income.py
──────────────────────────────────────────────────────────────────────────────
Computes income and expense for any portfolio, calendar, and period.

Sources (from compute_classifications.py):
  INCOME_ACCOUNTS  — DividendReceipt, InterestIncome, FXGainTradeSettle,
                     FXGainCurrency, AccruedInterestIncome, OptionIncome, etc.
  EXPENSE_ACCOUNTS — DividendExpense, InterestExpense

These are the same journal entries that feed the balance sheet revenue/
expense section and the performance TWR income component.
Nothing to reconcile — one source, multiple views.

Output shapes:
  detail   — one row per journal entry (full audit trail)
  summary  — one row per investment per income type
  total    — one row per investment, all income types summed

Drop into:
  financial_information_gateway/fig_code/compute_income.py

Register in compute_registry.py:
  COMPUTE_REGISTRY["compute_income"] = compute_income
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_classifications import (
    INCOME_ACCOUNTS,
    EXPENSE_ACCOUNTS,
    REVENUE_EXPENSE_ACCOUNTS,
    ACCOUNT_CLASSIFICATION,
    Category,
)

TOLERANCE = 1e-6

# All income and expense accounts combined
ALL_INCOME_EXPENSE = INCOME_ACCOUNTS | EXPENSE_ACCOUNTS


# ──────────────────────────────────────────────────────────────────────────────
# EXTRACTION
# ──────────────────────────────────────────────────────────────────────────────

def _extract_income(prep, uber_filter=None) -> pd.DataFrame:
    """
    Extract all income and expense journal entries for the period.
    Signs are as they appear in the journals — flipped for display
    in the shaping step (income is typically a credit = negative book).
    """
    prior_cutoff   = prep["prior_cutoff_datetime"]
    current_cutoff = prep["current_cutoff_datetime"]

    rows = []

    for je in prep["journal_entries"]:
        fa  = getattr(je, "financial_account", None)
        inv = getattr(je, "investment", None)

        if fa not in ALL_INCOME_EXPENSE:
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
            "ibor_date":         getattr(je, "ibor_date",   None),
            "trade_date":        getattr(je, "tradedate",   None),
            "settle_date":       getattr(je, "settledate",  None),
            "transaction":       getattr(je, "transaction", None),
            "tranid":            getattr(je, "tranid",      None),
            "financial_account": fa,
            "category":          category,
            "income_type":       _income_type_label(fa),
            "local":             getattr(je, "local",       0.0),
            "book":              getattr(je, "book",        0.0),
            "is_adjustment":     is_adj,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _income_type_label(fa: str) -> str:
    """Human-readable income type label for a financial account."""
    labels = {
        "DividendReceipt":          "Dividend",
        "DividendExpense":          "Dividend Expense",
        "FXGainTradeSettle":        "FX Gain — Trade Settlement",
        "FXGainCurrency":           "FX Gain — Currency",
        "InterestIncome":           "Interest Income",
        "InterestReceipt":          "Interest Receipt",
        "InterestExpense":          "Interest Expense",
        "AccruedInterestIncome":    "Accrued Interest Income",
        "AccruedInterestReceipt":   "Accrued Interest Receipt",
        "UnearnedIncome":           "Unearned Income",
        "OptionIncome":             "Option Income",
        "PurchasedInterestExpense": "Purchased Interest Expense",
        "SoldInterestIncome":       "Sold Interest Income",
    }
    return labels.get(fa, fa)


# ──────────────────────────────────────────────────────────────────────────────
# SHAPE — SUMMARY VIEW
# ──────────────────────────────────────────────────────────────────────────────

def _shape_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Summarise income by investment and income type.
    Flips sign so income appears as a positive number.
    (Income accounts are credits in double-entry — negative in journals.)
    """
    if df.empty:
        return pd.DataFrame()

    summary = (
        df.groupby(["investment", "income_type", "financial_account"])
        [["local", "book"]]
        .sum()
        .reset_index()
    )

    # Flip sign — income is a credit (negative in journals)
    summary["income_local"] = -summary["local"]
    summary["income_book"]  = -summary["book"]
    summary = summary.drop(columns=["local", "book"])

    summary = summary.sort_values(
        ["investment", "financial_account"]
    ).reset_index(drop=True)

    return summary


# ──────────────────────────────────────────────────────────────────────────────
# SHAPE — TOTAL VIEW
# ──────────────────────────────────────────────────────────────────────────────

def _shape_total(df: pd.DataFrame) -> pd.DataFrame:
    """
    Total income per investment across all income types.
    """
    if df.empty:
        return pd.DataFrame()

    total = (
        df.groupby("investment")[["local", "book"]]
        .sum()
        .reset_index()
    )

    total["income_local"] = -total["local"]
    total["income_book"]  = -total["book"]
    total = total.drop(columns=["local", "book"])

    # Grand total row
    grand = pd.DataFrame([{
        "investment":   "── TOTAL",
        "income_local": total["income_local"].sum(),
        "income_book":  total["income_book"].sum(),
    }])

    total = pd.concat([total, grand], ignore_index=True)

    return total


# ──────────────────────────────────────────────────────────────────────────────
# SUBTOTALS FOR DETAIL/SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

def _add_investment_subtotals(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-investment subtotals and grand total."""
    if df.empty:
        return df

    numeric_cols = [c for c in ["income_local", "income_book"] if c in df.columns]
    subtotal_rows = []

    for inv, group in df.groupby("investment"):
        sub = {col: group[col].sum() for col in numeric_cols}
        sub.update({
            "investment":        inv,
            "financial_account": "── Subtotal",
            "income_type":       "── Subtotal",
            "row_type":          "subtotal",
        })
        subtotal_rows.append(sub)

    grand = {col: df[col].sum() for col in numeric_cols}
    grand.update({
        "investment":        "── TOTAL",
        "financial_account": "── Grand Total",
        "income_type":       "── Grand Total",
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

def compute_income(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
    shape:        str            = "summary",  # "detail", "summary", "total"
) -> ComputeResult:
    """
    Compute income and expense for a portfolio, calendar, and period range.

    shape parameter controls output:
      "detail"  — one row per journal entry (full audit trail)
      "summary" — one row per investment per income type (default)
      "total"   — one row per investment, all types summed

    Income signs are flipped from journal representation so income
    appears as a positive number in the output.

    These entries are the same journals that feed the balance sheet
    revenue/expense section and the TWR income component.
    """

    t_total = time.perf_counter()

    if prep is None:
        raise ValueError("prep is required.")

    if shape not in ("detail", "summary", "total"):
        raise ValueError(
            f"Invalid shape '{shape}'. Use 'detail', 'summary', or 'total'."
        )

    # Extract
    t_extract = time.perf_counter()
    raw_df = _extract_income(prep, uber_filter)
    t_extract_ms = (time.perf_counter() - t_extract) * 1000

    if raw_df.empty:
        return ComputeResult(
            function="compute_income",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="income",
            data=pd.DataFrame(),
            valid=True,
            errors=[],
            metadata={"note": "No income entries in this period"},
        )

    # Shape
    t_shape = time.perf_counter()

    if shape == "detail":
        # Flip sign on raw detail rows
        output_df = raw_df.copy()
        output_df["income_local"] = -output_df["local"]
        output_df["income_book"]  = -output_df["book"]
        output_df = output_df.drop(columns=["local", "book"])
        output_df = _add_investment_subtotals(output_df)

    elif shape == "summary":
        output_df = _shape_summary(raw_df)
        output_df = _add_investment_subtotals(output_df)

    else:  # total
        output_df = _shape_total(raw_df)

    t_shape_ms = (time.perf_counter() - t_shape) * 1000
    t_total_ms = (time.perf_counter() - t_total) * 1000

    n_investments = raw_df["investment"].nunique()
    n_entries     = len(raw_df)

    print(
        f">>> compute_income COMPLETE "
        f"| {portfolio} | {calendar} "
        f"| {period_start} → {period_end} "
        f"| {n_investments} investments "
        f"| {n_entries} income entries "
        f"| shape={shape} "
        f"| {t_total_ms:.0f}ms"
    )

    metadata = {
        "elapsed_ms":   round(t_total_ms, 1),
        "extract_ms":   round(t_extract_ms, 1),
        "shape_ms":     round(t_shape_ms, 1),
        "investments":  n_investments,
        "income_entries": n_entries,
        "shape":        shape,
        "uber_filter":  uber_filter,
    }

    return ComputeResult(
        function="compute_income",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="income",
        data=output_df,
        valid=True,
        errors=[],
        metadata=metadata,
    )
