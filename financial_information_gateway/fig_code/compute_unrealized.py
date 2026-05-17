"""
compute_unrealized.py
Thin wrapper over compute_accounting_ledger filtered to UNREALIZED_ACCOUNTS.
UnrealPriceGL, UnrealFXGL. Offset accounts excluded (stat only).
Accounting accuracy is credibility.
"""

from __future__ import annotations
from typing import Optional
import pandas as pd

from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_accounting_ledger import compute_accounting_ledger
from financial_information_gateway.fig_code.compute_classifications import (
    UNREALIZED_ACCOUNTS,
    add_summary_rows,
)


def compute_unrealized(
    portfolio:    str,
    calendar:     str,
    period_start: str,
    period_end:   str,
    uber_filter:  Optional[dict] = None,
    prep:         Optional[dict] = None,
    ppa_ibor_date=None,
) -> ComputeResult:
    """
    Unrealized ledger.
    Opening + Activity + Closing for every unrealized account.
    Includes investment subtotals and grand total rows.
    Thin wrapper over compute_accounting_ledger filtered to UNREALIZED_ACCOUNTS.
    """
    result = compute_accounting_ledger(
        portfolio=portfolio, calendar=calendar,
        period_start=period_start, period_end=period_end,
        uber_filter=uber_filter, prep=prep,
        ppa_ibor_date=ppa_ibor_date,
    )

    if result.data is not None and not result.data.empty:
        df = result.data[
            result.data["financial_account"].isin(UNREALIZED_ACCOUNTS)
        ].copy().reset_index(drop=True)
        df = add_summary_rows(df)
    else:
        df = pd.DataFrame()

    return ComputeResult(
        function="compute_unrealized",
        portfolio=portfolio, calendar=calendar,
        period_start=period_start, period_end=period_end,
        shape="unrealized",
        data=df, valid=result.valid, errors=result.errors,
        metadata={
            **result.metadata,
            "category":          "Unrealized",
            "accounts_included": sorted(UNREALIZED_ACCOUNTS),
            "rows_after_filter": len(df),
        },
    )