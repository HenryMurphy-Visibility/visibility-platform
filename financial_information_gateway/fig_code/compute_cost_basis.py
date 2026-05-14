"""
compute_cost_basis.py
──────────────────────────────────────────────────────────────────────────────
Cost basis ledger — Category 1 of 5.

Shows opening balance, period activity, and closing balance
for all cost basis accounts. Quantity, local, and book.

Accounts covered (from compute_classifications.py):
  Cost                    — settled position cost basis
  Receivable              — trade receivables
  Payable                 — trade payables
  AccruedInterestReceivable / Payable
  DividendsReceivable / Payable
  SpotFxReceivable / Payable
  ForwardFxReceivable / Payable
  InterestReceivable / Payable
  SoldAccruedReceivable
  PurchasedAccruedPayable
  Expenses_Receivable / ExpensesPayable
  SoldAccrued / PurchasedAccrued

This is a thin wrapper over compute_accounting_ledger.
Same opening/activity/closing structure.
Filtered to cost basis accounts only.

Accounting accuracy is credibility.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Optional

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_accounting_ledger import (
    compute_accounting_ledger,
)
from financial_information_gateway.fig_code.compute_classifications import (
    COST_BASIS_ACCOUNTS,
)


def compute_cost_basis(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
    ppa_ibor_date=None,
) -> ComputeResult:
    """
    Cost basis ledger.

    Opening + Activity + Closing for every cost basis account.
    Quantity, local, and book — all three dimensions.

    Thin wrapper over compute_accounting_ledger filtered to
    COST_BASIS_ACCOUNTS from compute_classifications.py.

    Parameters
    ----------
    portfolio     : Portfolio identifier e.g. "Portfolio1"
    calendar      : Calendar name e.g. "Monthly"
    period_start  : Period start key e.g. "2021-01"
    period_end    : Period end key e.g. "2021-01"
    uber_filter   : Optional investment filter e.g. {"investment": "GOOG"}
    prep          : Pre-loaded prep dict from prep_state (required)
    ppa_ibor_date : IBOR date for prior period adjustments
    """

    # ── CALL FOUNDATION ──────────────────────────────────────────────
    result = compute_accounting_ledger(
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        uber_filter=uber_filter,
        prep=prep,
        ppa_ibor_date=ppa_ibor_date,
    )

    # ── FILTER TO COST BASIS ACCOUNTS ────────────────────────────────
    if result.data is not None and not result.data.empty:
        df = result.data[
            result.data["financial_account"].isin(COST_BASIS_ACCOUNTS)
        ].copy().reset_index(drop=True)
    else:
        import pandas as pd
        df = pd.DataFrame()

    # ── RETURN WITH CORRECT SHAPE ─────────────────────────────────────
    return ComputeResult(
        function="compute_cost_basis",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="cost_basis",
        data=df,
        valid=result.valid,
        errors=result.errors,
        metadata={
            **result.metadata,
            "category":           "Cost Basis",
            "accounts_included":  sorted(COST_BASIS_ACCOUNTS),
            "rows_after_filter":  len(df),
        },
    )