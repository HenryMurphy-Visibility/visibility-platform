"""
compute_realized.py
Thin wrapper over compute_accounting_ledger filtered to REALIZED_ACCOUNTS.
PriceGainInvestment, FXGainInvestment, FXGainCurrency, FXGainTradeSettle.
Accounting accuracy is credibility.
"""

from __future__ import annotations
from typing import Optional
import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_accounting_ledger import compute_accounting_ledger
from financial_information_gateway.fig_code.compute_classifications import (
    REALIZED_ACCOUNTS,
    add_summary_rows,
)


def compute_realized(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
    ppa_ibor_date=None,
) -> ComputeResult:
    """
    Realized ledger.
    Opening + Activity + Closing for every realized account.
    Includes investment subtotals and grand total rows.
    Thin wrapper over compute_accounting_ledger filtered to REALIZED_ACCOUNTS.
    """
    result = compute_accounting_ledger(
        portfolio=portfolio, calendar=calendar,
        period_start=period_start, period_end=period_end,
        uber_filter=uber_filter, prep=prep,
        ppa_ibor_date=ppa_ibor_date,
    )

    if result.data is not None and not result.data.empty:
        df = result.data[
            result.data["financial_account"].isin(REALIZED_ACCOUNTS)
        ].copy().reset_index(drop=True)
        df = add_summary_rows(df)
    else:
        df = pd.DataFrame()

    return ComputeResult(
        function="compute_realized",
        portfolio=portfolio, calendar=calendar,
        period_start=period_start, period_end=period_end,
        shape="realized",
        data=df, valid=result.valid, errors=result.errors,
        metadata={
            **result.metadata,
            "category":          "Realized",
            "accounts_included": sorted(REALIZED_ACCOUNTS),
            "rows_after_filter": len(df),
        },
    )