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

from financial_information_gateway.fig_code.compute_performance_summary import compute_performance_summary
from financial_information_gateway.fig_code.compute_performance import (
    compute_performance,
    clear_performance_cache,
)
from financial_information_gateway.fig_code.compute_recon import compute_recon
from financial_information_gateway.fig_code.api.app_routes import router

from cph_routes       import cph_router
from ops_routes       import ops_router
from oversight_routes import oversight_router
from tips_routes      import tips_router
from auth_routes      import auth_router
from auth_manager     import init_auth
from auth_middleware  import AuthMiddleware
from v_config         import CHEST_PATH


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

    # ── AUTH ──────────────────────────────────────────────
    init_auth(CHEST_PATH)
    print(">>> Auth initialized")

    print(">>> Building price and FX indexes...")
    _ensure_price_index()
    print(">>> Price index ready")

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

from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── MIDDLEWARE — order matters ─────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

# ── ROUTERS ────────────────────────────────────────────────
app.include_router(router)
app.include_router(cph_router)
app.include_router(ops_router)
app.include_router(oversight_router)
app.include_router(tips_router)
app.include_router(auth_router)

from fastapi import Request
from fastapi.responses import JSONResponse


# ============================================================
# LOGIN PAGE
# ============================================================

@app.get("/login", response_class=HTMLResponse)
def login_page():
    import os
    login_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "login.html")
    with open(login_path, "r", encoding="utf-8") as f:
        return f.read()


# ============================================================
# LANDING PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
def landing():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Visibility — Financial Information Platform</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,300;0,400;0,600;1,300;1,400&family=JetBrains+Mono:wght@300;400&display=swap');

        :root {
            --bg:      #07080f;
            --surface: #0d0f1a;
            --border:  #1a1e2e;
            --accent:  #2E5FA3;
            --accent2: #4a7fc1;
            --text:    #d8dce8;
            --muted:   #5a6080;
            --gold:    #e6a817;
            --mono:    'JetBrains Mono', monospace;
            --serif:   'Crimson Pro', Georgia, serif;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            background: var(--bg);
            color: var(--text);
            font-family: var(--serif);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 60px 40px;
        }

        body::before {
            content: '';
            position: fixed;
            top: 0; left: 50%;
            transform: translateX(-50%);
            width: 600px; height: 400px;
            background: radial-gradient(ellipse at center top,
                rgba(46,95,163,0.12) 0%, transparent 70%);
            pointer-events: none;
        }

        .container {
            max-width: 720px;
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0;
        }

        .brand {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 20px;
            margin-bottom: 48px;
        }

        .brand img {
            width: 96px; height: 96px;
            object-fit: contain;
            opacity: 0.92;
            filter: drop-shadow(0 0 24px rgba(46,95,163,0.4));
        }

        .brand-title {
            font-family: var(--serif);
            font-size: 3.2em;
            font-weight: 300;
            letter-spacing: 8px;
            text-transform: uppercase;
            color: #fff;
            line-height: 1;
        }

        .brand-sub {
            font-family: var(--mono);
            font-size: 0.68em;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: var(--accent2);
            margin-top: -8px;
        }

        .divider {
            width: 100%;
            height: 1px;
            background: linear-gradient(90deg,
                transparent, var(--accent), transparent);
            margin-bottom: 40px;
        }

        .welcome {
            text-align: center;
            margin-bottom: 52px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .welcome p {
            font-family: var(--serif);
            font-size: 1.15em;
            color: #b0b8cc;
            line-height: 1.85;
            font-weight: 300;
        }

        .welcome p.lead {
            font-size: 1.25em;
            color: var(--text);
        }

        .welcome p.closing {
            font-family: var(--mono);
            font-size: 0.75em;
            letter-spacing: 1px;
            color: var(--muted);
            margin-top: 8px;
        }

        .welcome .exclusive {
            font-family: var(--mono);
            font-size: 0.72em;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--gold);
            background: rgba(230,168,23,0.07);
            border: 1px solid rgba(230,168,23,0.2);
            padding: 8px 20px;
            display: inline-block;
            margin: 0 auto;
        }

        .consoles {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            justify-content: center;
            width: 100%;
            margin-bottom: 40px;
        }

        .console-btn {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 5px;
            padding: 18px 32px;
            text-decoration: none;
            border: 1px solid var(--border);
            background: var(--surface);
            transition: all 0.2s;
            min-width: 120px;
        }
        .console-btn:hover {
            border-color: var(--accent);
            background: rgba(46,95,163,0.1);
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(46,95,163,0.2);
        }
        .console-btn.primary {
            border-color: rgba(46,95,163,0.4);
            background: rgba(46,95,163,0.08);
        }
        .console-btn.primary:hover {
            border-color: var(--accent2);
            background: rgba(46,95,163,0.18);
        }
        .console-btn.oversight {
            border-color: rgba(184,134,11,0.3);
            background: rgba(184,134,11,0.05);
        }
        .console-btn.oversight:hover {
            border-color: var(--gold);
            background: rgba(184,134,11,0.12);
        }
        .console-btn.stub {
            opacity: 0.35;
            cursor: default;
            pointer-events: none;
        }

        .console-label {
            font-family: var(--mono);
            font-size: 0.9em;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: #fff;
        }
        .console-btn.oversight .console-label { color: var(--gold); }

        .console-desc {
            font-family: var(--mono);
            font-size: 0.58em;
            letter-spacing: 1px;
            color: var(--muted);
            text-transform: uppercase;
        }

        .footer {
            font-family: var(--mono);
            font-size: 0.62em;
            color: #2a3050;
            letter-spacing: 1px;
            text-align: center;
            padding-top: 24px;
            border-top: 1px solid var(--border);
            width: 100%;
        }
    </style>
</head>
<body>
<div class="container">

    <div class="brand">
        <img src="/static/visibility.png" alt="Visibility">
        <div class="brand-title">Visibility</div>
        <div class="brand-sub">Financial Information Platform</div>
    </div>

    <div class="divider"></div>

    <div class="welcome">

        <div class="exclusive">Invitation Only</div>

        <p class="lead">
            What you are seeing is a live, working financial information system
            unlike anything currently available.
        </p>

        <p>
            Built on a temporal, event-driven architecture, Visibility redefines
            what investment accounting software can be — not as an incremental
            improvement on legacy platforms, but as a different foundation entirely.
        </p>

        <p>
            This is not a demo environment. This is the system in active
            development — processing real data, generating real journal entries,
            in real time. No database. No reconciliation layer. No compromises
            made in the name of convention.
        </p>

        <p>
            Few possessed the cross between Silicon Valley and Wall Street experience to see what was missing — and fewer still recognized, three years ago, that the convergence of domain expertise, artificial intelligence, and modern architecture created a singular opportunity to build something entirely new from the ground up. Visibility is the result of that vision
        </p>

        <p>
            Access to this environment is by invitation only.
            You are among the first to see it.
        </p>

        <p class="closing">Thank you for your interest.</p>

    </div>

    <div class="consoles">
        <a href="/ops" class="console-btn primary">
            <span class="console-label">OPS</span>
            <span class="console-desc">Operations</span>
        </a>
        <a href="/fig" class="console-btn primary">
            <span class="console-label">FIG</span>
            <span class="console-desc">Reports</span>
        </a>
        <a href="/cph" class="console-btn primary">
            <span class="console-label">CPH</span>
            <span class="console-desc">Processing</span>
        </a>
        <a href="/oversight" class="console-btn oversight">
            <span class="console-label">Oversight</span>
            <span class="console-desc">Governance</span>
        </a>
        <a class="console-btn stub">
            <span class="console-label">FA</span>
            <span class="console-desc">Coming Soon</span>
        </a>
        <a class="console-btn stub">
            <span class="console-label">PERF</span>
            <span class="console-desc">Coming Soon</span>
        </a>
    </div>

    <div class="footer">
        Visibility &nbsp;·&nbsp; Chest Financial Systems &nbsp;·&nbsp;
        Henry J. Murphy, Founder &nbsp;·&nbsp; Confidential
    </div>

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
@app.get("/api/v1/performance/summary")
def compute_performance_summary_endpoint(
    portfolio:    str           = Query(...),
    calendar:     str           = Query(...),
    period_start: str           = Query(...),
    period_end:   str           = Query(...),
    level:        str           = Query("investment"),
    investment:   Optional[str] = Query(None),
    page:         int           = Query(1, ge=1),
    page_size:    int           = Query(1000, ge=1, le=10000),
):
    try:
        uber_filter = {"investment": investment.upper()} if investment else None
        prep        = prep_state(portfolio, calendar, period_start, period_end)
        result      = compute_performance_summary(
            portfolio=portfolio, calendar=calendar,
            period_start=period_start, period_end=period_end,
            level=level,
            uber_filter=uber_filter, prep=prep,
        )
        return render(result, target="api", options={"page": page, "page_size": page_size})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
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
# ============================================================

@app.post("/api/v1/compute/{function_name}")
def compute_endpoint(
    function_name: str,
    params:        dict,
):
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