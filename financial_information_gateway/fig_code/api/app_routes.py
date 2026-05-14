"""
app_routes.py
financial_information_gateway/fig_code/api/app_routes.py

All rev/exp and balance sheet endpoints.
Registered in app.py via:
    from financial_information_gateway.fig_code.api.app_routes import router
    app.include_router(router)
"""

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
import traceback
import io

from financial_information_gateway.fig_code.fig_core import prep_state, render
from financial_information_gateway.fig_code.compute_income import compute_income
from financial_information_gateway.fig_code.compute_capital import compute_capital
from financial_information_gateway.fig_code.compute_unrealized import compute_unrealized
from financial_information_gateway.fig_code.compute_realized_gains import compute_realized_gains
from financial_information_gateway.fig_code.compute_balance_sheet import compute_balance_sheet

router = APIRouter()

PERIOD_FORMAT_GUIDE = (
    "Period format by calendar — "
    "Yearly: YYYY (e.g. 2021) · "
    "Quarterly: YYYY-QN (e.g. 2021-Q1) · "
    "Monthly: YYYY-MM (e.g. 2021-01) · "
    "Daily: YYYY-MM-DD (e.g. 2021-01-15)"
)

# ============================================================
# COMPUTE BALANCE SHEET
# ============================================================

@router.get("/api/v1/balance-sheet")
def compute_balance_sheet_endpoint(
    portfolio:    str           = Query(...,   description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,   description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,   description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,   description="Period end key — same format as period_start."),
    investment:   Optional[str] = Query(None,  description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    summary_only: bool          = Query(False, description="True returns section subtotals and grand total only."),
    page:         int           = Query(1,     ge=1),
    page_size:    int           = Query(1000,  ge=1, le=10000),
):
    """
    ## Balance Sheet (compute_balance_sheet)

    Complete balance sheet for the period.
    Every account. Opening balances, period movements, closing balances.
    Classified by economic category. Grouped by section.

    Sections:
      Assets      — Cost, Receivables, Accrued Interest, Unrealized Gains
      Liabilities — Payables
      Revenue     — Income, Realized Price Gain, Realized FX Gain
      Expenses    — Expense accounts
      Capital     — Contributed Cost / capital flows

    Invariant verified for every row: Opening + Movement = Closing

    This is the spine. Every other report is a view of this output.
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_balance_sheet(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep, summary_only=summary_only,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/balance-sheet/csv")
def compute_balance_sheet_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
    summary_only: bool          = Query(False),
):
    """Balance Sheet — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_balance_sheet(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep, summary_only=summary_only,
        )
        df = result.data
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No data returned")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_balance_sheet{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# COMPUTE INCOME
# ============================================================

@router.get("/api/v1/income")
def compute_income_endpoint(
    portfolio:    str           = Query(...,       description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,       description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,       description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,       description="Period end key — same format as period_start."),
    investment:   Optional[str] = Query(None,      description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    shape:        str           = Query("summary", description="detail · summary · total"),
    page:         int           = Query(1,         ge=1),
    page_size:    int           = Query(1000,      ge=1, le=10000),
):
    """
    ## Income (compute_income)

    Revenue and expense account movements for the period.
    Dividends, interest, FX gains on settlement, option income.

    Same journal entries that feed the balance sheet revenue section
    and the TWR income component. One source. No reconciliation.

    shape: detail | summary (default) | total
    Income appears as positive.
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_income(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep, shape=shape,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/income/csv")
def compute_income_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
    shape:        str           = Query("summary"),
):
    """Income — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_income(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep, shape=shape,
        )
        df = result.data
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No data returned")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_income{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# COMPUTE CAPITAL
# ============================================================

@router.get("/api/v1/capital")
def compute_capital_endpoint(
    portfolio:    str           = Query(...,       description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,       description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,       description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,       description="Period end key — same format as period_start."),
    investment:   Optional[str] = Query(None,      description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    shape:        str           = Query("summary", description="detail · summary"),
    page:         int           = Query(1,         ge=1),
    page_size:    int           = Query(1000,      ge=1, le=10000),
):
    """
    ## Capital Flows (compute_capital)

    External cash movements — contributions and withdrawals.
    ContributedCost journal entries.

    Same entries that form the TWR cash flow denominator and
    the balance sheet capital section.

    Opening NAV + Capital + Income + Realized + Unrealized Change
    = Closing NAV. The recon endpoint proves this.

    shape: detail | summary (default)
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_capital(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep, shape=shape,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/capital/csv")
def compute_capital_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
    shape:        str           = Query("summary"),
):
    """Capital Flows — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_capital(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep, shape=shape,
        )
        df = result.data
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No data returned")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_capital{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# COMPUTE UNREALIZED
# ============================================================

@router.get("/api/v1/unrealized")
def compute_unrealized_endpoint(
    portfolio:    str           = Query(...,  description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,  description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,  description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,  description="Period end key — same format as period_start."),
    investment:   Optional[str] = Query(None, description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
):
    """
    ## Unrealized Gain/Loss (compute_unrealized)

    Proves unrealized gain two ways and shows they agree.

    Method A — Journal roll-up:
      Sum of UnrealPriceGL, UnrealFXGL and offset account movements.
      The accounting view.

    Method B — Point-in-time state:
      UnrealPriceGL + UnrealFXGL balances at period end.
      The appraisal view.

    ties: true for every investment means perfect agreement
    between accounting and appraisal views of unrealized gain.
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_unrealized(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/unrealized/csv")
def compute_unrealized_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
):
    """Unrealized Gain/Loss — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_unrealized(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep,
        )
        df = result.data
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No data returned")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_unrealized{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# COMPUTE REALIZED GAINS
# ============================================================

@router.get("/api/v1/realized-gains")
def compute_realized_gains_endpoint(
    portfolio:    str           = Query(...,   description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,   description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,   description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,   description="Period end key — same format as period_start."),
    investment:   Optional[str] = Query(None,  description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    summary_only: bool          = Query(False, description="True returns investment subtotals only."),
    page:         int           = Query(1,     ge=1),
    page_size:    int           = Query(1000,  ge=1, le=10000),
):
    """
    ## Realized Gains (compute_realized_gains)

    Realized gains and losses at lot level for the period.

    Sources:
      PriceGainInvestment — realized price gain on disposed lots
      FXGainInvestment    — realized FX gain on disposed lots

    One row per disposition event. Price gain and FX gain shown
    separately. Investment subtotals and grand total included.

    Same journal entries that feed the balance sheet revenue section
    and the performance TWR. One source. No reconciliation.
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_realized_gains(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep, summary_only=summary_only,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/realized-gains/csv")
def compute_realized_gains_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
    summary_only: bool          = Query(False),
):
    """Realized Gains — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_realized_gains(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, prep=prep, summary_only=summary_only,
        )
        df = result.data
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No data returned")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_realized_gains{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))