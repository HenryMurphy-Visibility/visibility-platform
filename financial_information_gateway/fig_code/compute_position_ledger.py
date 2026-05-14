# ============================================================
# Visibility — Compute Position Ledger
# compute_position_ledger.py
#
# Position-level ledger — tax lots collapsed to investment level.
#
# Structure per investment:
#   OPENING       — all lots summed to one row
#   ACTIVITY      — full Cost JE detail (one row per journal entry)
#   ACTIVITY_TOTAL — net activity for the investment
#   CLOSING       — all lots summed to one row
#
# For full tax lot detail use compute_accounting_ledger.
# For point-in-time appraisal use compute_appraisal.
# ============================================================

import pandas as pd
from datetime import datetime

from financial_information_gateway.fig_code.fig_core import prep_state
from financial_information_gateway.fig_code.compute_result import ComputeResult
from financial_information_gateway.fig_code.compute_accounting_ledger import (
    compute_accounting_ledger,
)


# ============================================================
# COMPUTE POSITION LEDGER — PUBLIC INTERFACE
# ============================================================

def compute_position_ledger(
        portfolio,
        calendar,
        period_start,
        period_end,
        uber_filter=None,
        prep=None,
        ppa_ibor_date=None
):
    """
    Position-level ledger — tax lots collapsed to investment level.

    Opening and closing balances are summed across all lots
    to produce one row per investment. Activity shows full
    Cost account journal entry detail plus a subtotal per
    investment.

    Parameters
    ----------
    portfolio     : str  — portfolio identifier
    calendar      : str  — calendar name
    period_start  : str  — period start YYYY-MM
    period_end    : str  — period end YYYY-MM
    uber_filter   : dict — optional e.g. {"investment": "GOOG"}
                         pass None for full portfolio
    prep          : dict — optional pre-loaded prep package
    ppa_ibor_date : datetime — PPA IBOR date

    Returns
    -------
    ComputeResult with shape='position_ledger'
    """

    start_time = datetime.now()

    # --------------------------------------------------
    # GET LOT-LEVEL LEDGER FROM compute_accounting_ledger
    # --------------------------------------------------
    lot_result = compute_accounting_ledger(
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        uber_filter=uber_filter,
        prep=prep,
        ppa_ibor_date=ppa_ibor_date,
    )

    if lot_result.data is None or lot_result.data.empty:
        return ComputeResult(
            function="compute_position_ledger",
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            shape="position_ledger",
            data=pd.DataFrame(),
            valid=lot_result.valid,
            errors=lot_result.errors,
            metadata={}
        )

    df = lot_result.data.copy()

    # --------------------------------------------------
    # SEPARATE INTO THREE SECTIONS
    # --------------------------------------------------
    opening_df  = df[df["event_type"] == "OPENING"].copy()
    closing_df  = df[df["event_type"] == "CLOSING"].copy()

    # Activity — Cost account JEs only
    # These explain position changes
    # Valuation and rev/exp entries belong on other reports
    activity_df = df[
        (df["event_type"] == "ACTIVITY") &
        (df["financial_account"] == "Cost")
    ].copy()

    # --------------------------------------------------
    # COLLAPSE OPENING — sum lots per investment
    # --------------------------------------------------
    opening_grouped = (
        opening_df
        .groupby("investment", sort=True)
        .agg(
            ibor_date=("ibor_date", "first"),
            qty=      ("qty",       "sum"),
            local=    ("local",     "sum"),
            book=     ("book",      "sum"),
        )
        .reset_index()
    )
    opening_grouped["event_type"]  = "OPENING"
    opening_grouped["transaction"] = None
    opening_grouped["sequence"]    = -1

    # --------------------------------------------------
    # ACTIVITY — full Cost JE detail + subtotal
    # --------------------------------------------------
    if not activity_df.empty:

        # Keep full detail rows
        activity_detail = activity_df[[
            "investment",
            "transaction",
            "ibor_date",
            "qty",
            "local",
            "book",
            "sequence",
            "financial_account",
        ]].copy()
        activity_detail["event_type"] = "ACTIVITY"

        # Subtotal per investment
        activity_sub = (
            activity_df
            .groupby("investment", sort=True)
            .agg(
                ibor_date=("ibor_date", "first"),
                qty=      ("qty",       "sum"),
                local=    ("local",     "sum"),
                book=     ("book",      "sum"),
            )
            .reset_index()
        )
        activity_sub["event_type"]  = "ACTIVITY_TOTAL"
        activity_sub["transaction"] = "TOTAL"
        activity_sub["sequence"]    = 999997

    else:
        activity_detail = pd.DataFrame()
        activity_sub    = pd.DataFrame()

    # --------------------------------------------------
    # COLLAPSE CLOSING — sum lots per investment
    # --------------------------------------------------
    closing_grouped = (
        closing_df
        .groupby("investment", sort=True)
        .agg(
            ibor_date=("ibor_date", "first"),
            qty=      ("qty",       "sum"),
            local=    ("local",     "sum"),
            book=     ("book",      "sum"),
        )
        .reset_index()
    )
    closing_grouped["event_type"]  = "CLOSING"
    closing_grouped["transaction"] = None
    closing_grouped["sequence"]    = 999999

    # --------------------------------------------------
    # PORTFOLIO TOTALS
    # --------------------------------------------------
    def portfolio_total(grouped_df, event_type, sequence):
        if grouped_df.empty:
            return pd.DataFrame()
        return pd.DataFrame([{
            "investment":  "TOTAL",
            "event_type":  event_type,
            "transaction": None,
            "ibor_date":   grouped_df["ibor_date"].iloc[0],
            "qty":         grouped_df["qty"].sum(),
            "local":       grouped_df["local"].sum(),
            "book":        grouped_df["book"].sum(),
            "sequence":    sequence,
        }])

    opening_total = portfolio_total(opening_grouped, "OPENING_TOTAL", -2)
    closing_total = portfolio_total(closing_grouped, "CLOSING_TOTAL", 999998)

    # --------------------------------------------------
    # COMBINE IN DISPLAY ORDER
    # --------------------------------------------------
    frames = []

    if not opening_grouped.empty:
        frames.append(opening_grouped)
    if not opening_total.empty:
        frames.append(opening_total)

    if not activity_detail.empty:
        frames.append(activity_detail)
    if not activity_sub.empty:
        frames.append(activity_sub)

    if not closing_grouped.empty:
        frames.append(closing_grouped)
    if not closing_total.empty:
        frames.append(closing_total)

    result_df = pd.concat(frames, ignore_index=True)

    # --------------------------------------------------
    # FORMAT NUMBERS
    # --------------------------------------------------
    for col in ["qty", "local", "book"]:
        if col in result_df.columns:
            result_df[col] = result_df[col].apply(
                lambda x: f"{x:,.2f}"
                if isinstance(x, (int, float)) and x == x
                else ""
            )

    result_df = result_df.fillna("")

    # --------------------------------------------------
    # COLUMN ORDER
    # --------------------------------------------------
    col_order = [
        "event_type",
        "investment",
        "transaction",
        "ibor_date",
        "financial_account",
        "qty",
        "local",
        "book",
    ]

    col_order  = [c for c in col_order if c in result_df.columns]
    result_df  = result_df[col_order]

    # --------------------------------------------------
    # METADATA
    # --------------------------------------------------
    elapsed_ms  = (datetime.now() - start_time).total_seconds() * 1000
    investments = result_df[
        result_df["event_type"] == "OPENING"
    ]["investment"].nunique()

    metadata = {
        "row_count":   len(result_df),
        "investments": investments,
        "elapsed_ms":  round(elapsed_ms, 2),
        "uber_filter": uber_filter,
    }

    print(
        f">>> COMPUTE POSITION LEDGER COMPLETE "
        f"| {portfolio} | {calendar} "
        f"| {period_start} → {period_end} "
        f"| {investments} investments "
        f"| {len(result_df)} rows "
        f"| {round(elapsed_ms, 1)}ms"
    )

    return ComputeResult(
        function="compute_position_ledger",
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        shape="position_ledger",
        data=result_df,
        valid=lot_result.valid,
        errors=lot_result.errors,
        metadata=metadata,
    )