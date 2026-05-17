# ============================================================
# tips_routes.py
# Visibility — Contextual Intelligence API
#
# Serves tips from config/tips.json — no recompile needed.
# Add tips by editing the JSON file only.
#
# Endpoints:
#   GET /api/v1/tips              — all tips
#   GET /api/v1/tips?context=X   — tips for a specific context
#
# Contexts:
#   create_portfolio · add_investment · add_event
#   process · bootstrap · add_calendar
#   close_period · reopen_period · restate
#   cal_overview · validation
#
# Henry J. Murphy — Chest Financial Systems
# ============================================================

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Optional
import json

tips_router = APIRouter(prefix="/api/v1/tips", tags=["Tips"])

# Tips file lives in chest root /config/tips.json
_TIPS_PATH = Path(__file__).parent / "config" / "tips.json"


def _load_tips() -> list:
    """Load tips from JSON file. Returns empty list if file not found."""
    if not _TIPS_PATH.exists():
        return []
    with open(_TIPS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@tips_router.get("")
def get_tips(context: Optional[str] = Query(None)):
    """
    Return tips optionally filtered by context.

    Context maps to the current UI panel:
      create_portfolio, add_investment, add_event,
      process, bootstrap, close_period, reopen_period,
      restate, cal_overview, validation
    """
    tips = _load_tips()

    if context:
        tips = [t for t in tips if t.get("context") == context]

    return {
        "context": context or "all",
        "count":   len(tips),
        "tips":    tips,
    }