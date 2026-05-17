"""
app_routes.py
financial_information_gateway/fig_code/api/app_routes.py

All five balance sheet constituent endpoints plus recon.
Registered in app.py via:
    from financial_information_gateway.fig_code.api.app_routes import router
    app.include_router(router)
"""

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
import traceback
import io

from financial_information_gateway.fig_code.fig_core import render
from financial_information_gateway.fig_code.compute_cost_basis import compute_cost_basis
from financial_information_gateway.fig_code.compute_income import compute_income
from financial_information_gateway.fig_code.compute_realized import compute_realized
from financial_information_gateway.fig_code.compute_unrealized import compute_unrealized
from financial_information_gateway.fig_code.compute_capital import compute_capital

router = APIRouter()

PERIOD_FORMAT_GUIDE = (
    "Period format by calendar — "
    "Yearly: YYYY (e.g. 2021) · "
    "Quarterly: YYYY-QN (e.g. 2021-Q1) · "
    "Monthly: YYYY-MM (e.g. 2021-01) · "
    "Daily: YYYY-MM-DD (e.g. 2021-01-15)"
)


# ──────────────────────────────────────────────────────────────────────────────
# SHARED CSV HELPER
# ──────────────────────────────────────────────────────────────────────────────

def _csv_response(df, filename):
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No data returned")
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. COST BASIS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/cost-basis")
def cost_basis_endpoint(
    portfolio:    str           = Query(...,  description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,  description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,  description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,  description="Period end key — same format as period_start"),
    investment:   Optional[str] = Query(None, description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
):
    """
    ## Cost Basis Ledger

    Opening + Activity + Closing for every cost basis account.
    Quantity, local, and book — all three dimensions.

    Accounts: Cost, Receivable, Payable, AccruedInterest,
              DividendsReceivable/Payable, SpotFx/ForwardFx,
              InterestReceivable/Payable and related accounts.

    Every lot that opened during the period shows Opening=0.
    Every lot that existed before shows its opening balance.
    Activity = journal entries. Closing = current state.
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_cost_basis(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/cost-basis/csv")
def cost_basis_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
):
    """Cost Basis — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_cost_basis(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_cost_basis{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return _csv_response(result.data, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# 2. INCOME
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/income")
def income_endpoint(
    portfolio:    str           = Query(...,  description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,  description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,  description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,  description="Period end key — same format as period_start"),
    investment:   Optional[str] = Query(None, description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
):
    """
    ## Income Ledger

    Opening + Activity + Closing for every income and expense account.

    Accounts: DividendReceipt, InterestIncome, InterestReceipt,
              AccruedInterestIncome, AccruedInterestReceipt,
              UnearnedIncome, OptionIncome, SoldInterestIncome,
              DividendExpense, InterestExpense, MgmtFee, PerfFee
              and related accounts.

    Income appears as credits in journals.
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_income(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/income/csv")
def income_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
):
    """Income — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_income(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_income{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return _csv_response(result.data, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# 3. REALIZED
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/realized")
def realized_endpoint(
    portfolio:    str           = Query(...,  description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,  description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,  description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,  description="Period end key — same format as period_start"),
    investment:   Optional[str] = Query(None, description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
):
    """
    ## Realized Gains Ledger

    Opening + Activity + Closing for every realized gain/loss account.

    Accounts: PriceGainInvestment, FXGainInvestment,
              FXGainCurrency, FXGainTradeSettle

    Each activity row is one disposition event.
    Gains appear as credits (negative in journals).
    Losses appear as debits (positive in journals).
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_realized(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/realized/csv")
def realized_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
):
    """Realized Gains — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_realized(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_realized{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return _csv_response(result.data, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# 4. UNREALIZED
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/unrealized")
def unrealized_endpoint(
    portfolio:    str           = Query(...,  description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,  description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,  description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,  description="Period end key — same format as period_start"),
    investment:   Optional[str] = Query(None, description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
):
    """
    ## Unrealized Gains Ledger

    Opening + Activity + Closing for every unrealized gain/loss account.

    Accounts: UnrealPriceGL, UnrealFXGL
    Excluded: UnrealPriceGLOffset, UnrealFXGLOffset (stat only)

    Each activity row is one daily valuation posting.
    The closing balance is the cumulative unrealized position.
    This closing balance satisfies: Cost + Unrealized = MarketVal
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_unrealized(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/unrealized/csv")
def unrealized_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
):
    """Unrealized Gains — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_unrealized(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_unrealized{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return _csv_response(result.data, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# 5. CAPITAL
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/capital")
def capital_endpoint(
    portfolio:    str           = Query(...,  description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,  description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,  description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,  description="Period end key — same format as period_start"),
    investment:   Optional[str] = Query(None, description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
):
    """
    ## Capital Ledger

    Opening + Activity + Closing for every capital flow account.

    Accounts: ContributedCost

    Each activity row is one capital contribution or withdrawal.
    At investment level: in-kind contributions carry cost basis
    and unrealized for correct performance flow treatment.
    At portfolio level: external cash flows.
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_capital(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/capital/csv")
def capital_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
):
    """Capital — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment is not None else None
        result = compute_capital(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter,
        )
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_capital{inv_part}_{portfolio}_{calendar}_{period_start}_{period_end}.csv"
        return _csv_response(result.data, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))