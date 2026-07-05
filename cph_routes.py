# ============================================================
# cph_routes.py
# Central Processing Hub — REST API Routes
#
# Processing endpoints. Registered in app.py via:
#   from cph_routes import cph_router
#   app.include_router(cph_router)
#
# Deliberately separate from FIG reporting routes.
# FIG reads state. CPH writes state.
# These are different operations and belong in different layers.
#
# PHASE-2 WRITE GATE
# ------------------
# Processing/build endpoints (bootstrap, process, cache clear) call
# _gate_writes() as their first line. The gate is OFF unless the machine
# sets VISIBILITY_WRITES_ENABLED=1 in its environment:
#   - Dev box: set VISIBILITY_WRITES_ENABLED=1 → processing works.
#   - Cloud:   never set it → processing returns the Phase-2 message; the
#              read-only status endpoint stays open.
# Same env var as ops_routes, so data entry and processing move together.
# Same code on both machines — nothing to edit per-deploy, survives git pull.
# ============================================================

import os
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import traceback

from process_portfolio import bootstrap_portfolio, run_all_periods

cph_router = APIRouter(prefix="/api/v1/cph", tags=["Processing"])


# ============================================================
# PHASE-2 WRITE GATE
# ============================================================

WRITES_ENABLED = os.getenv("VISIBILITY_WRITES_ENABLED", "0") == "0"

_GATE_MESSAGE = (
    "Processing and data entry are enabled in Phase 2 evaluation, "
    "available to firms advancing to early-adoption assessment."
)


def _gate_writes():
    """Raise 403 with the Phase-2 message when writes are disabled.

    First line of every processing/build endpoint. The console's existing
    error display surfaces this verbatim, so a gated call reads as a
    deliberate access tier rather than a crash.
    """
    if not WRITES_ENABLED:
        raise HTTPException(status_code=403, detail=_GATE_MESSAGE)


# ============================================================
# BOOTSTRAP
# ============================================================

@cph_router.post("/bootstrap")
def bootstrap_endpoint(
    portfolio: str  = Query(...,   description="Portfolio identifier e.g. Portfolio1"),
    force:     bool = Query(False, description="Force rebuild even if candidates already exist"),
):
    """
    ## Bootstrap Portfolio

    Builds the self-contained portfolio world from global master files.

    Steps:
      1. Derives candidate investments from event history
      2. Extracts portfolio-specific Investment Master from global IM
      3. Extracts portfolio-specific Bond Info from global bond info
      4. Saves Candidates/candidates.json

    Safe to call repeatedly — skips if already built unless force=True.
    """
    _gate_writes()
    try:
        result = bootstrap_portfolio(portfolio, force=force)
        return {
            "portfolio":        portfolio,
            "status":           "complete",
            "investment_count": result["investment_count"],
            "bond_count":       result["bond_count"],
            "currencies":       sorted(result["currencies"]),
            "candidates":       len(result["candidates"]),
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# PROCESS — single period or all periods
# ============================================================

@cph_router.post("/process")
def process_endpoint(
    portfolio:   str           = Query(...,   description="Portfolio identifier e.g. Portfolio1"),
    calendar:    str           = Query(...,   description="Calendar name: Monthly · Daily · Quarterly · Yearly"),
    period_name: Optional[str] = Query(None,  description="Period name e.g. 2021-01. Omit for all periods."),
    bootstrap:   bool          = Query(False, description="Force bootstrap rebuild before processing"),
):
    """
    ## Process Portfolio

    Triggers CPH processing for a portfolio and calendar.

    Bootstraps portfolio world automatically if not already built.
    Pass bootstrap=true to force a rebuild of the candidate list
    and portfolio-specific reference data.

    If period_name is provided — processes that period only.
    If omitted — processes all periods in the calendar.

    Returns period metrics including journal entry counts,
    adjusting entry counts, and processing time per period.

    Note: Processing time shown is V-side CPH time only.
    Event loading time is not included in per-period metrics.
    """
    _gate_writes()
    try:
        # Bootstrap if needed or forced
        bootstrap_portfolio(portfolio, force=bootstrap)

        # Run processing
        metrics = run_all_periods(
            portfolio=portfolio,
            calendar=calendar,
            period_name=period_name,
        )

        # Aggregate totals
        total_regular   = sum(m.get("regular_journal_entries", 0) for m in metrics)
        total_adjusting = sum(m.get("adjusting_journal_entries", 0) for m in metrics)
        total_time      = sum(m.get("total_time", 0.0) for m in metrics)

        return {
            "portfolio":          portfolio,
            "calendar":           calendar,
            "period_name":        period_name or "all",
            "periods_processed":  len(metrics),
            "total_regular_je":   total_regular,
            "total_adjusting_je": total_adjusting,
            "total_time_seconds": round(total_time, 3),
            "periods":            [
                {
                    "period_name":        m.get("period_name"),
                    "regular_je":         m.get("regular_journal_entries", 0),
                    "adjusting_je":       m.get("adjusting_journal_entries", 0),
                    "time_seconds":       round(m.get("total_time", 0.0), 3),
                    "passes_executed":    m.get("passes_executed", []),
                }
                for m in metrics
            ],
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# STATUS — portfolio processing status  (read-only — OPEN)
# ============================================================

@cph_router.get("/status/{portfolio}")
def status_endpoint(portfolio: str):
    """
    ## Portfolio Status

    Returns the current status of a portfolio's processing world.

    Shows whether bootstrap has been run, how many candidates
    are registered, and when the candidate list was last updated.
    """
    import json
    import os
    from v_config import FUNDS_PATH
    from pathlib import Path

    try:
        candidates_path = (
            Path(FUNDS_PATH) / portfolio / "Candidates" / "candidates.json"
        )

        if not candidates_path.exists():
            return {
                "portfolio":    portfolio,
                "bootstrapped": False,
                "candidates":   0,
                "currencies":   [],
                "last_updated": None,
            }

        with open(candidates_path) as f:
            data = json.load(f)

        return {
            "portfolio":    portfolio,
            "bootstrapped": True,
            "candidates":   data.get("count", 0),
            "currencies":   data.get("currencies", []),
            "last_updated": data.get("last_updated"),
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# CACHE CONTROL
# ============================================================

from process_portfolio import clear_event_cache

@cph_router.post("/cache/clear")
def clear_cache_endpoint(
    portfolio: Optional[str] = Query(None, description="Portfolio to clear. Omit for all portfolios."),
):
    """
    ## Clear Event Cache

    Clears the in-memory event cache for a portfolio or all portfolios.
    Call this when new events arrive and you want to force a fresh load.
    Watchdog will call this automatically when new event files are detected.
    """
    _gate_writes()
    clear_event_cache(portfolio)
    return {
        "status":    "cleared",
        "portfolio": portfolio or "all",
    }