# ============================================================
# Visibility — REST API
# financial_information_gateway/fig_code/api/app.py
#
# Start the server from the chest root:
#   uvicorn financial_information_gateway.fig_code.api.app:app
#   --host 127.0.0.1 --port 8000
#
# Interactive docs: http://127.0.0.1:8000/api/v1/docs
# Landing page:     http://127.0.0.1:8000
# ============================================================

from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from datetime import datetime
from typing import Optional
import traceback
import io

from financial_information_gateway.fig_code.compute_registry import (
    COMPUTE_REGISTRY,
    list_compute_functions,
)
from financial_information_gateway.fig_code.compute_accounting_ledger import (
    compute_accounting_ledger,
)
from financial_information_gateway.fig_code.compute_appraisal import (
    compute_appraisal,
    _ensure_price_index,
)
from financial_information_gateway.fig_code.compute_position_ledger import (
    compute_position_ledger,
)
from financial_information_gateway.fig_code.fig_core import (
    prep_state,
    render,
)
from financial_information_gateway.fig_code.compute_performance import (
    compute_performance,
    clear_performance_cache,
)
from financial_information_gateway.fig_code.compute_recon import compute_recon
from financial_information_gateway.fig_code.api.app_routes import router

from cph_routes import cph_router

from ops_routes import ops_router

from oversight_routes import oversight_router

from tips_routes import tips_router



# ============================================================
# PERIOD FORMAT GUIDE
# ============================================================

PERIOD_FORMAT_GUIDE = (
    "Period format by calendar — "
    "Yearly: YYYY (e.g. 2021) · "
    "Quarterly: YYYY-QN (e.g. 2021-Q1) · "
    "Monthly: YYYY-MM (e.g. 2021-01) · "
    "Daily: YYYY-MM-DD (e.g. 2021-01-15)"
)

def _parse_period_start(period_start: str) -> datetime:
    """Parse period_start to datetime regardless of calendar format."""
    if 'Q' in period_start:
        year, q = period_start.split('-Q')
        return datetime(int(year), (int(q) - 1) * 3 + 1, 1)
    if len(period_start) == 4:
        return datetime(int(period_start), 1, 1)
    if len(period_start) == 7:
        return datetime.strptime(period_start + "-01", "%Y-%m-%d")
    return datetime.strptime(period_start, "%Y-%m-%d")

# ============================================================
# STARTUP
# ============================================================

@asynccontextmanager
async def lifespan(app):
    print("=" * 60)
    print("  VISIBILITY — Financial Information Gateway")
    print("  Starting up...")
    print("=" * 60)

    print(">>> Building price and FX indexes...")
    _ensure_price_index()
    print(">>> Price index ready")

    # ── PERFORMANCE CACHE — uncomment for production ──────────
    # print(">>> Building performance cache...")
    # try:
    #     prep = prep_state("Portfolio1", "Monthly", "2021-01", "2025-12")
    #     compute_performance(
    #         portfolio="Portfolio1",
    #         calendar="Monthly",
    #         period_start="2021-01",
    #         period_end="2025-12",
    #         level="investment",
    #         cadence=None,
    #         uber_filter=None,
    #         prep=prep,
    #     )
    #     print(">>> Performance cache ready")
    # except Exception as e:
    #     print(f">>> Performance cache build FAILED: {e}")
    #     traceback.print_exc()
    #     print(">>> Server will continue")

    print(">>> All indexes ready — accepting requests")
    print("=" * 60)
    yield
    print(">>> Server shutting down")


# ============================================================
# APP INSTANCE
# ============================================================

app = FastAPI(
    title="Visibility — Financial Information Gateway",
    description=(
        "Institutional-grade investment accounting API. "
        "Every compute function available as a REST endpoint. "
        "All results derived from consistent, state-based "
        "accounting architecture.\n\n"
        "**Period formats:** "
        "Yearly=YYYY · Quarterly=YYYY-QN · "
        "Monthly=YYYY-MM · Daily=YYYY-MM-DD\n\n"
        "**Available calendars:** "
        "Yearly · Quarterly · Monthly · Daily · Operational"
    ),
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request
from fastapi.responses import JSONResponse

# ============================================================
# IP WHITELIST
# Add allowed IP addresses here.
# "127.0.0.1" = localhost (always allow for your own testing)
# Add ngrok recipient IPs as needed
# ============================================================
#
# ALLOWED_IPS = {
#     "127.0.0.1",       # localhost — always allowed
#     "::1",             # localhost IPv6
#     "2605:59ca:4246:5808:40e0:c5bd:2dd3:5cdb",
#     "2600:1700:2923:1020:4906:2069:f7b9:67f1",
#      "2601:195:8180:2520:2866:66f7:82ef:2901",
#     "192.168.1.27"
#     # "203.0.113.45",  # example — add recipient IPs here
# }
#
# @app.middleware("http")
# async def ip_whitelist(request: Request, call_next):
#     client_ip = request.client.host
#     if client_ip not in ALLOWED_IPS:
#         return JSONResponse(
#             status_code=403,
#             content={"detail": f"Access denied."}
#         )
#     return await call_next(request)
# Register all rev/exp and balance sheet routes
app.include_router(router)
app.include_router(cph_router)# After existing include_router lines
app.include_router(ops_router)

app.include_router(oversight_router)

app.include_router(tips_router)



# ============================================================
# LANDING PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
def landing():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Visibility — Financial Information Gateway</title>
    <style>
        body { font-family: Georgia, serif; max-width: 800px; margin: 0 auto; padding: 60px 40px; background: #0a0a1a; color: #e8e8e8; line-height: 1.8; }
        h1 { font-size: 2.4em; color: #ffffff; border-bottom: 1px solid #2E5FA3; padding-bottom: 20px; margin-bottom: 10px; }
        .version { color: #888; font-size: 0.9em; margin-bottom: 40px; }
        h2 { color: #2E5FA3; margin-top: 60px; font-size: 1.3em; }
        p { margin: 16px 0; }
        .metric { font-size: 1.1em; color: #ffffff; font-weight: bold; margin: 8px 0; padding-left: 20px; border-left: 2px solid #2E5FA3; }
        .question { border-left: 3px solid #2E5FA3; padding: 10px 20px; margin: 16px 0; font-style: italic; color: #cccccc; }
        .killer { font-weight: bold; color: #ffffff; font-size: 1.05em; margin: 40px 0; padding: 24px; border: 1px solid #2E5FA3; line-height: 1.9; }
        .disclaimer { font-size: 0.9em; color: #888; font-style: italic; margin: 40px 0; padding: 20px; border-left: 2px solid #444; }
        .targeting { font-size: 0.95em; color: #aaa; margin: 40px 0; padding: 20px; border: 1px solid #333; }
        .get-started { display: block; margin: 80px auto 60px auto; padding: 20px 60px; background: #2E5FA3; color: white; font-size: 1.1em; border: none; cursor: pointer; text-decoration: none; text-align: center; letter-spacing: 2px; font-family: Georgia, serif; }
        .get-started:hover { background: #1F3864; }
        .footer { margin-top: 80px; padding-top: 20px; border-top: 1px solid #222; color: #555; font-size: 0.85em; text-align: center; }
    </style>
</head>
<body>
    <h1>Visibility</h1>
    <p class="version">Financial Information Gateway &nbsp;·&nbsp; Version 1.0 &nbsp;·&nbsp; Invitation Only</p>

    <h2>A 50-Year Problem</h2>
    <p>Every investment firm knows the landscape. Multiple systems. Multiple schemas. Reconciliation processes that run continuously. Teams whose primary function is validating that different parts of the technology stack agree with each other.</p>
    <p>This is not the result of bad decisions. It is the accumulated consequence of a structural problem that has resisted every attempt to fix it.</p>
    <p style="color: #ffffff; font-weight: bold; margin-top: 30px;">Visibility addresses the root problem.</p>

    <h2>What You Are About to See</h2>
    <p>This API exposes the reporting layer of a working investment accounting system built on a different foundation — event-driven, state-based, and consistent by construction.</p>

    <p class="disclaimer">
        The dataset behind this demonstration is purpose-built — modelled to reflect real-world conditions while remaining focused enough for you to verify both accuracy and scale independently. It is intentionally not a showcase of functional breadth.<br><br>
        That is an entirely different conversation — one we look forward to having.
    </p>

    <h2>The Numbers</h2>
    <p class="metric">504 investments &nbsp;·&nbsp; five-year history</p>
    <p class="metric">180,000+ trades &nbsp;·&nbsp; 3.8 million journal entries</p>
    <p class="metric">1,300+ immutably stored states across four calendars</p>
    <p class="metric">Daily · Monthly · Quarterly · Yearly — simultaneously</p>
    <p class="metric">Full portfolio appraisal: 3.7 seconds · Pure Python · No database · Laptop hardware</p>
    <p class="metric">826,320 price observations indexed · 182,111 journals loaded</p>

    <h2>The Questions Worth Asking</h2>
    <p class="question">Can your system restate any closed period and propagate the correction through all subsequent periods automatically?</p>
    <p class="question">Can your system produce daily performance at the investment level as a direct output of your accounting architecture — not a separate process?</p>
    <p class="question">Can your system maintain unlimited period history across any number of simultaneous calendars with full consistency?</p>
    <p class="question">Can your system process a correction across five years of history in seconds?</p>
    <p class="question">Can your system produce operations, fund accounting, and management reporting from a single consistent source of truth with no reconciliation between them?</p>

    <p class="killer">
        If you answered no to any or all of these questions — can you envision the productivity that could be achieved with the logical restructuring of your workflows and the elimination of reconciliation points between them?
    </p>

    <p class="targeting">
        <strong>Who this is for:</strong><br><br>
        Visibility is built for organizations with the technical and domain expertise to build on a proven foundation — not for those seeking a turnkey solution out of the box.<br><br>
        If your team includes sophisticated engineers and domain experts who have long wanted a coherent architectural foundation to build against rather than another layer of workarounds — this is built for you.<br><br>
        If you are looking for a fully configured off-the-shelf system today — Visibility is not yet that product. But it will be. And when it is, the firms that built on the foundation early will have shaped it. We welcome that conversation too.
    </p>

    <p style="color: #888; margin-top: 40px;">What follows is not a presentation. It is a working system.</p>
    <p style="color: #888;">The data is real. The response times are real. The consistency is real.</p>
    <p style="color: #888;">When you are ready —</p>
 
<div style="display:flex; gap:16px; justify-content:center; margin: 80px auto 60px auto;">
    <a href="/ops" style="padding: 20px 48px; background: #2E5FA3; color: white; font-size: 1.1em; text-decoration: none; text-align: center; letter-spacing: 2px; font-family: Georgia, serif; display:flex; flex-direction:column; gap:4px;">
        <span>OPS</span>
        <span style="font-size:0.55em; letter-spacing:1px; opacity:0.8;">Operations Console</span>
    </a>
    <a href="/fig" style="padding: 20px 48px; background: #2E5FA3; color: white; font-size: 1.1em; text-decoration: none; text-align: center; letter-spacing: 2px; font-family: Georgia, serif; display:flex; flex-direction:column; gap:4px;">
        <span>FIG</span>
        <span style="font-size:0.55em; letter-spacing:1px; opacity:0.8;">Financial Information Gateway</span>
    </a>
    <a href="/cph" style="padding: 20px 48px; background: #2E5FA3; color: white; font-size: 1.1em; text-decoration: none; text-align: center; letter-spacing: 2px; font-family: Georgia, serif; display:flex; flex-direction:column; gap:4px;">
        <span>CPH</span>
        <span style="font-size:0.55em; letter-spacing:1px; opacity:0.8;">Central Processing Hub</span>
    </a>
    <a href="/api/v1/docs" style="padding: 20px 48px; background: transparent; color: #2E5FA3; font-size: 1.1em; text-decoration: none; text-align: center; letter-spacing: 2px; font-family: Georgia, serif; border: 1px solid #2E5FA3; display:flex; flex-direction:column; gap:4px;">
        <span>API DOCS</span>
        <span style="font-size:0.55em; letter-spacing:1px; opacity:0.8;">REST Interface</span>
    </a>
    <a href="/oversight" style="padding: 20px 48px; background: #7a5a08; color: #e6a817; font-size: 1.1em; text-decoration: none; text-align: center; letter-spacing: 2px; font-family: Georgia, serif; border: 1px solid #b8860b; display:flex; flex-direction:column; gap:4px;">
         <span>Oversight</span>
         <span style="font-size:0.55em; letter-spacing:1px; opacity:0.8;">Governance Console</span>
</a>
</div>
</div>
    <div class="footer">
        Visibility &nbsp;·&nbsp; Chest Financial Systems &nbsp;·&nbsp; Henry J. Murphy, Founder &nbsp;·&nbsp; Confidential
    </div>
</body>
</html>
"""

@app.get("/console", response_class=HTMLResponse)
def console():
    """Visibility compute console."""
    import os
    console_path = os.path.join(os.path.dirname(__file__), "console.html")
    with open(console_path, "r") as f:
        return f.read()

# After the /console route
@app.get("/fig", response_class=HTMLResponse)
def fig_console():
    import os
    console_path = os.path.join(os.path.dirname(__file__), "console.html")
    with open(console_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/cph", response_class=HTMLResponse)
def cph_console():
    import os
    cph_path = os.path.join(os.path.dirname(__file__), "cph.html")
    with open(cph_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/ops", response_class=HTMLResponse)
def ops_console():
    import os
    ops_path = os.path.join(os.path.dirname(__file__), "ops.html")
    with open(ops_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/oversight", response_class=HTMLResponse)
def oversight_console():
    import os
    oversight_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "oversight.html")
    with open(oversight_path, "r", encoding="utf-8") as f:
        return f.read()
# ============================================================
# HEALTH
# ============================================================

@app.get("/api/v1/health")
def health():
    return {
        "status":            "ok",
        "version":           "1.0.0",
        "compute_functions": list(COMPUTE_REGISTRY.keys()),
        "timestamp":         datetime.now().isoformat(),
    }


# ============================================================
# REGISTRY
# ============================================================

@app.get("/api/v1/registry")
def registry():
    return {
        "functions": list_compute_functions(),
        "count":     len(COMPUTE_REGISTRY),
    }


# ============================================================
# COMPUTE ACCOUNTING LEDGER
# ============================================================

@app.get("/api/v1/ledger")
def compute_accounting_ledger_endpoint(
    portfolio:    str           = Query(...,  description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,  description="Calendar name: Yearly · Quarterly · Monthly · Daily · Operational"),
    period_start: str           = Query(...,  description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,  description="Period end key — same format as period_start."),
    investment:   Optional[str] = Query(None, description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
    ppa_date:     Optional[str] = Query(None, description="PPA IBOR date YYYY-MM-DD. Defaults to first day of period."),
):

    print(f">>> LEDGER | ppa_date={ppa_date} | period_start={period_start} | period_end={period_end}")
    """
    ## Accounting Ledger (compute_accounting_ledger)

    Complete financial state at tax lot level.
    Every account. Every lot. Every journal entry.
    Opening balances, activity, and closing balances —
    consistent by construction.
    """
    try:
        uber_filter   = {"investment": investment} if investment else None
        ppa_ibor_date = (
            datetime.strptime(ppa_date, "%Y-%m-%d")
            if ppa_date else
            _parse_period_start(period_start)
        )
        result = compute_accounting_ledger(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, ppa_ibor_date=ppa_ibor_date,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/ledger/csv")
def compute_accounting_ledger_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
    ppa_date:     Optional[str] = Query(None),
):
    """Accounting Ledger — CSV Download"""
    try:
        uber_filter   = {"investment": investment} if investment else None
        ppa_ibor_date = (
            datetime.strptime(ppa_date, "%Y-%m-%d")
            if ppa_date else
            _parse_period_start(period_start)
        )
        result = compute_accounting_ledger(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, ppa_ibor_date=ppa_ibor_date,
        )
        df = result.data
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No data returned")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_ledger{inv_part}_{portfolio}_{calendar}_{period_end}.csv"
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
# COMPUTE APPRAISAL
# ============================================================

@app.get("/api/v1/appraisal")
def compute_appraisal_endpoint(
    portfolio:    str           = Query(...,            description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,            description="Calendar name: Yearly · Quarterly · Monthly · Daily · Operational"),
    period_start: str           = Query(...,            description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,            description="Period end key — same format as period_start."),
    mode:         str           = Query("period_close", description="period_open · period_close (default)"),
    investment:   Optional[str] = Query(None,           description="Filter by investment ticker e.g. GOOG."),
    summary_only: bool          = Query(False,          description="True returns subtotals and totals only."),
    page:         int           = Query(1,              ge=1),
    page_size:    int           = Query(500,            ge=1, le=5000),
):
    """
    ## Portfolio Appraisal (compute_appraisal)

    Point-in-time appraisal at tax lot level.
    Market value and price gain calculated fresh from price data.
    504 investments · 17,575 lots · 826,320 price observations.
    Full portfolio: ~3.7 seconds V-side.
    """
    try:
        uber_filter = {"investment": investment} if investment else None
        result      = compute_appraisal(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            mode=mode, uber_filter=uber_filter,
        )
        if summary_only and result.data is not None and not result.data.empty:
            result.data = result.data[
                result.data["row_type"].isin(["subtotal", "type_total", "grand_total"])
            ].copy()
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/appraisal/csv")
def compute_appraisal_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    mode:         str           = Query("period_close"),
    investment:   Optional[str] = Query(None),
    summary_only: bool          = Query(False),
):
    """Appraisal — CSV Download"""
    try:
        uber_filter = {"investment": investment} if investment else None
        result      = compute_appraisal(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            mode=mode, uber_filter=uber_filter,
        )
        df = result.data
        if summary_only and df is not None and not df.empty:
            df = df[df["row_type"].isin(["subtotal", "type_total", "grand_total"])].copy()
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No data returned")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_appraisal{inv_part}_{portfolio}_{calendar}_{period_end}_{mode}.csv"
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
# COMPUTE POSITION LEDGER
# ============================================================

@app.get("/api/v1/position-ledger")
def compute_position_ledger_endpoint(
    portfolio:    str           = Query(...,  description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,  description="Calendar name: Yearly · Quarterly · Monthly · Daily · Operational"),
    period_start: str           = Query(...,  description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,  description="Period end key — same format as period_start."),
    investment:   Optional[str] = Query(None, description="Filter by investment ticker e.g. GOOG."),
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
):
    """
    ## Position Ledger (compute_position_ledger)

    Position-level ledger — tax lots collapsed to investment level.
    Opening balance, period activity, closing balance per investment.
    """
    try:
        uber_filter   = {"investment": investment} if investment else None
        ppa_ibor_date = _parse_period_start(period_start)
        result        = compute_position_ledger(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, ppa_ibor_date=ppa_ibor_date,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/position-ledger/csv")
def compute_position_ledger_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    investment:   Optional[str] = Query(None),
):
    """Position Ledger — CSV Download"""
    try:
        uber_filter   = {"investment": investment} if investment else None
        ppa_ibor_date = _parse_period_start(period_start)
        result        = compute_position_ledger(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            uber_filter=uber_filter, ppa_ibor_date=ppa_ibor_date,
        )
        df = result.data
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No data returned")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        inv_part = f"_{investment}" if investment else "_portfolio"
        filename = f"visibility_position_ledger{inv_part}_{portfolio}_{calendar}_{period_end}.csv"
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
# COMPUTE PERFORMANCE
# ============================================================

@app.get("/api/v1/performance")
def compute_performance_endpoint(
    portfolio:    str           = Query(...,          description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,          description="Calendar name: Yearly · Quarterly · Monthly · Daily · Operational"),
    period_start: str           = Query(...,          description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,          description="Period end key — same format as period_start."),
    level:        str           = Query("investment", description="investment · sector · analyst · country · currency · asset_class · portfolio"),
    cadence:      Optional[str] = Query(None,         description="Omit=full range · D=daily · M=monthly · Q=quarterly · Y=yearly"),
    investment:   Optional[str] = Query(None,         description="Filter by investment ticker e.g. GOOG."),
    page:         int           = Query(1,            ge=1),
    page_size:    int           = Query(1000,         ge=1, le=10000),
):
    """
    ## Performance (compute_performance)

    Chained Time-Weighted Returns for any period range, level, and cadence.
    Daily grain is always the computational foundation.
    Period_Index chained across all periods — unbroken from day 1.
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_performance(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            level=level, cadence=cadence if cadence else None,
            uber_filter=uber_filter, prep=prep,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/performance/csv")
def compute_performance_csv(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    level:        str           = Query("investment"),
    cadence:      Optional[str] = Query(None),
    investment:   Optional[str] = Query(None),
):
    """Performance — CSV Download"""
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_performance(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            level=level, cadence=cadence if cadence else None,
            uber_filter=uber_filter, prep=prep,
        )
        df = result.data
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No data returned")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        inv_part = f"_{investment}" if investment else ""
        cad_part = f"_{cadence}"    if cadence    else "_full"
        filename = f"visibility_performance{inv_part}_{level}{cad_part}_{portfolio}_{period_start}_{period_end}.csv"
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
# COMPUTE RECON
# ============================================================

@app.get("/api/v1/recon")
def compute_recon_endpoint(
    portfolio:    str           = Query(...,  description="Portfolio identifier e.g. Portfolio1"),
    calendar:     str           = Query(...,  description="Calendar name: Yearly · Quarterly · Monthly · Daily"),
    period_start: str           = Query(...,  description=PERIOD_FORMAT_GUIDE),
    period_end:   str           = Query(...,  description="Period end key — same format as period_start."),
    investment:   Optional[str] = Query(None, description="Filter by investment ticker e.g. GOOG. Omit for full portfolio."),
    unrealized:   bool          = Query(True, description="Include unrealized bridge recon"),
    page:         int           = Query(1,    ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
):
    """
    ## Master Reconciliation (compute_recon)

    Proves the complete NAV equation for every investment:

        Opening NAV
        + Capital Flows
        + Income
        + Realized Gains
        + Change in Unrealized
        = Closing NAV

    Look for **all_clear: true** in the performance block.

    This is not a reconciliation process.
    It is a proof that the architecture makes one unnecessary.
    """
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result = compute_recon(
            portfolio=portfolio,
            calendar=calendar,
            period_start=period_start,
            period_end=period_end,
            uber_filter=uber_filter,
            prep=prep,
            include_view1=True,
            include_view2=True,
            include_view3=False,
            include_cross_view=True,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GENERIC COMPUTE ENDPOINT
# Builds prep_state automatically from request body params.
# ============================================================

@app.post("/api/v1/compute/{function_name}")
def compute_endpoint(
    function_name: str,
    params:        dict,
):
    """
    ## Generic Compute Endpoint

    Calls any registered compute function by name.
    prep_state built automatically from portfolio, calendar,
    period_start, period_end in the request body.

    Use /api/v1/registry to see all available functions.
    """
    if function_name not in COMPUTE_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown: '{function_name}'. Available: {list(COMPUTE_REGISTRY.keys())}",
        )
    try:
        if "prep" not in params or params.get("prep") is None:
            p  = params.get("portfolio")
            c  = params.get("calendar")
            ps = params.get("period_start")
            pe = params.get("period_end")
            if all([p, c, ps, pe]):
                params["prep"] = prep_state(p, c, ps, pe)
        result = COMPUTE_REGISTRY[function_name](**params)
        return render(result, target="api")
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
