"""
app_performance_addition.py
──────────────────────────────────────────────────────────────────────────────
Add these blocks to app.py in the locations indicated.
This is NOT a standalone file — it shows exactly what to add and where.
──────────────────────────────────────────────────────────────────────────────
"""

# ============================================================================
# 1. ADD TO IMPORTS (top of app.py, with other compute imports)
# ============================================================================

from financial_information_gateway.fig_code.compute_performance import compute_performance

# ============================================================================
# 2. ADD TO COMPUTE_REGISTRY (in compute_registry.py)
# ============================================================================

# In compute_registry.py, add:
#
#   from financial_information_gateway.fig_code.compute_performance import compute_performance
#   COMPUTE_REGISTRY["compute_performance"] = compute_performance

# ============================================================================
# 3. ADD PERIOD FORMAT GUIDE ADDITION (append to existing PERIOD_FORMAT_GUIDE)
# ============================================================================

PERFORMANCE_QUERY_GUIDE = """
Performance Level Values:
  investment     → one row per investment ticker
  sector         → aggregated by sector (from investment_master)
  analyst        → aggregated by analyst
  country        → aggregated by country
  currency       → aggregated by currency
  asset_class    → aggregated by asset class
  portfolio      → single portfolio total row

Performance Cadence Values:
  (omit)         → full range summary — one row per level value, total return
  D              → daily detail — full chained daily state
  M              → monthly carved periods
  Q              → quarterly carved periods
  Y              → yearly carved periods

Example URLs:
  /api/v1/performance?portfolio=Portfolio1&calendar=Monthly&period_start=2021-01&period_end=2025-12&level=investment&cadence=M
  /api/v1/performance?portfolio=Portfolio1&calendar=Monthly&period_start=2021-01&period_end=2025-12&level=sector&cadence=Q
  /api/v1/performance?portfolio=Portfolio1&calendar=Monthly&period_start=2021-01&period_end=2025-12&level=investment&uber_filter=GOOG
"""

# ============================================================================
# 4. ADD ENDPOINTS (add after existing ledger/appraisal/position endpoints)
# ============================================================================

from fastapi import Query
from fastapi.responses import StreamingResponse
import io

@app.get("/api/v1/performance", tags=["Performance"])
async def compute_performance_endpoint(
    portfolio: str = Query("Portfolio1", description="Portfolio name"),
    calendar: str = Query("Monthly", description="Calendar name"),
    period_start: str = Query(..., description="Start period key e.g. 2021-01"),
    period_end: str = Query(..., description="End period key e.g. 2025-12"),
    level: str = Query("investment", description=PERFORMANCE_QUERY_GUIDE),
    cadence: str = Query(None, description="None=full range, D=daily, M=monthly, Q=quarterly, Y=yearly"),
    uber_filter: str = Query(None, description="Single investment filter e.g. GOOG"),
):
    """
    Compute chained Time-Weighted Returns for the requested range, level, and cadence.

    Daily grain is always the foundation. Period_Index is chained across periods.
    Cadence controls how the result is presented, not how it is computed.
    """
    prep = prep_state(portfolio, calendar, period_start, period_end)

    uber = {"investment": uber_filter.upper()} if uber_filter else None

    result = compute_performance(
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        level=level,
        cadence=cadence if cadence else None,
        uber_filter=uber,
        prep=prep,
    )

    return _render_api(result)


@app.get("/api/v1/performance/csv", tags=["Performance"])
async def compute_performance_csv_endpoint(
    portfolio: str = Query("Portfolio1"),
    calendar: str = Query("Monthly"),
    period_start: str = Query(...),
    period_end: str = Query(...),
    level: str = Query("investment"),
    cadence: str = Query(None),
    uber_filter: str = Query(None),
):
    """
    Same as /api/v1/performance but returns a CSV download.
    """
    prep = prep_state(portfolio, calendar, period_start, period_end)

    uber = {"investment": uber_filter.upper()} if uber_filter else None

    result = compute_performance(
        portfolio=portfolio,
        calendar=calendar,
        period_start=period_start,
        period_end=period_end,
        level=level,
        cadence=cadence if cadence else None,
        uber_filter=uber,
        prep=prep,
    )

    buf = io.StringIO()
    result.data.to_csv(buf, index=False)
    buf.seek(0)

    filename = f"performance_{portfolio}_{level}_{period_start}_{period_end}.csv"
    if cadence:
        filename = f"performance_{portfolio}_{level}_{cadence}_{period_start}_{period_end}.csv"

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============================================================================
# 5. REGISTER IN COMPUTE_REGISTRY (compute_registry.py)
#    Add this line to the COMPUTE_REGISTRY dict alongside existing entries
# ============================================================================
#
#   "compute_performance": compute_performance,
#
# ============================================================================
