# ============================================================
# ops_routes.py
# Visibility — Operations REST API Routes
#
# Ops endpoints. Registered in app.py via:
#   from ops_routes import ops_router
#   app.include_router(ops_router)
#
# Ops is the gateway. Everything that enters the system
# goes through Ops. These endpoints express that workflow.
#
# Temporal methods — closing_method, accrual_method, amort_method
# are stored as histories. get_method_as_of() returns the
# correct value for any given date. No restatement needed.
# New selection simply appends to history.
#
# Non-temporal — base_currency, domicile_country, inception_date
# are foundational. Set once. Never changed.
#
# Temporal event corrections:
#   Reverse — stamps kdend on original. Event ceases to exist.
#   Modify  — reverse + new corrected record with kdbegin = kdend + 1ms
#
# Henry J. Murphy — Chest Financial Systems
# ============================================================

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
import traceback
import json
import os
import csv
from pathlib import Path
from datetime import datetime, timedelta

from v_config import FUNDS_PATH, REFDATA_PATH
from calendar_generator import generate_calendars, CALENDAR_PRESETS

ops_router = APIRouter(prefix="/api/v1/ops", tags=["Operations"])


# ============================================================
# MODELS
# ============================================================

class PortfolioConfig(BaseModel):
    portfolio_id:     str
    base_currency:    str             = "USD"
    domicile_country: str             = "US"
    inception_date:   str             # YYYY-MM-DD
    managers:         List[str]       = []
    description:      Optional[str]   = None
    closing_method:   str             = "FIFO"
    accrual_method:   str             = "accrue_eod"
    amort_method:     str             = "straight_line"
    calendars:        List[str]       = ["Monthly"]
    calendar_preset:  Optional[str]   = None


class InvestmentRecord(BaseModel):
    investment:       str
    full_name:        Optional[str]   = None
    investment_type:  str             = "EQUITY"
    currency:         str             = "USD"
    is_currency:      bool            = False
    country:          Optional[str]   = None
    asset_class:      Optional[str]   = None
    sector:           Optional[str]   = None
    analyst:          Optional[str]   = None
    pricing_factor:   float           = 1.0
    contract_size:    float           = 0.0
    underlying:       Optional[str]   = None
    put_call:         Optional[str]   = None
    strike:           Optional[float] = None


class EventRecord(BaseModel):
    portfolio:         str
    method:            str
    investment:        str
    tradedate:         str             # MM/DD/YYYY:HH:MM:SS
    settledate:        str
    kdbegin:           str
    kdend:             str             = "12/31/2099:00:00:00"
    payment_currency:  str             = "USD"
    location:          str             = ""
    strategy:          str             = ""
    quantity:          float           = 0.0
    price:             float           = 0.0
    notional:          float           = 0.0
    original_face:     float           = 0.0
    total_amount:      float           = 0.0
    total_amount_base: float           = 0.0
    accrued_local:     float           = 0.0
    accrued_book:      float           = 0.0
    buy_currency:      Optional[str]   = None
    sell_currency:     Optional[str]   = None
    buy_amt:           float           = 0.0
    sell_amt:          float           = 0.0
    mark_price:        float           = 0.0
    mark_fx:           float           = 0.0
    per_share:         float           = 0.0
    new_shares:        float           = 0.0
    old_shares:        float           = 0.0
    financial_account: Optional[str]   = None
    source:            str             = "manual"


class ReverseRequest(BaseModel):
    tranid:  int
    reason:  str  = ""
    actor:   str  = "ops"


class ModifyRequest(BaseModel):
    tranid:            int
    reason:            str
    actor:             str   = "ops"
    # Corrected fields — only supply what changed
    method:            Optional[str]   = None
    investment:        Optional[str]   = None
    tradedate:         Optional[str]   = None
    settledate:        Optional[str]   = None
    kdbegin:           Optional[str]   = None
    payment_currency:  Optional[str]   = None
    location:          Optional[str]   = None
    strategy:          Optional[str]   = None
    quantity:          Optional[float] = None
    price:             Optional[float] = None
    notional:          Optional[float] = None
    original_face:     Optional[float] = None
    total_amount:      Optional[float] = None
    total_amount_base: Optional[float] = None
    accrued_local:     Optional[float] = None
    accrued_book:      Optional[float] = None
    buy_currency:      Optional[str]   = None
    sell_currency:     Optional[str]   = None
    buy_amt:           Optional[float] = None
    sell_amt:          Optional[float] = None
    per_share:         Optional[float] = None
    new_shares:        Optional[float] = None
    old_shares:        Optional[float] = None
    financial_account: Optional[str]   = None


# ============================================================
# TEMPORAL METHOD HELPER
# ============================================================

def get_method_as_of(history: list, as_of_date: str) -> Optional[str]:
    if not history:
        return None
    applicable = [
        h for h in history
        if h.get("effective_from", "") <= as_of_date
    ]
    if not applicable:
        return history[0]["value"]
    return applicable[-1]["value"]


def get_portfolio_config(portfolio_id: str) -> dict:
    config_path = Path(FUNDS_PATH) / portfolio_id / "portfolio.json"
    if not config_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Portfolio '{portfolio_id}' not found"
        )
    with open(config_path) as f:
        return json.load(f)


def save_portfolio_config(portfolio_id: str, config: dict) -> None:
    config_path = Path(FUNDS_PATH) / portfolio_id / "portfolio.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


# ============================================================
# PORTFOLIO ENDPOINTS
# ============================================================

@ops_router.post("/portfolio")
def create_portfolio(config: PortfolioConfig):
    """
    ## Create Portfolio

    Creates a new portfolio with its complete directory structure
    and saves the portfolio configuration.
    """
    try:
        portfolio_id = config.portfolio_id.strip()

        if not portfolio_id:
            raise HTTPException(status_code=400, detail="portfolio_id is required")

        if not config.inception_date:
            raise HTTPException(status_code=400, detail="inception_date is required")

        portfolio_dir = Path(FUNDS_PATH) / portfolio_id

        if portfolio_dir.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Portfolio '{portfolio_id}' already exists"
            )

        # ── CREATE DIRECTORY STRUCTURE ────────────────────────────
        dirs = [
            portfolio_dir,
            portfolio_dir / "Candidates",
            portfolio_dir / "Events",
            portfolio_dir / "RefData",
            portfolio_dir / "Calendars",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # ── RESOLVE CALENDARS FROM PRESET OR EXPLICIT LIST ───────
        calendars = config.calendars
        if config.calendar_preset and config.calendar_preset in CALENDAR_PRESETS:
            calendars = CALENDAR_PRESETS[config.calendar_preset]
        if not calendars:
            calendars = ["Monthly"]

        # ── BUILD CONFIG WITH TEMPORAL METHOD HISTORIES ───────────
        config_data = {
            "portfolio_id":     portfolio_id,
            "base_currency":    config.base_currency,
            "domicile_country": config.domicile_country,
            "inception_date":   config.inception_date,
            "managers":         config.managers,
            "description":      config.description,
            "status":           "active",
            "created_at":       datetime.now().isoformat(),
            "calendars":        calendars,
            "closing_method_history": [
                {"value": config.closing_method, "effective_from": config.inception_date}
            ],
            "accrual_method_history": [
                {"value": config.accrual_method, "effective_from": config.inception_date}
            ],
            "amort_method_history": [
                {"value": config.amort_method, "effective_from": config.inception_date}
            ],
        }

        # ── SAVE PORTFOLIO CONFIG ─────────────────────────────────
        config_path = portfolio_dir / "portfolio.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)

        # ── GENERATE CALENDAR FILES ───────────────────────────────
        calendar_results = generate_calendars(
            portfolio      = portfolio_id,
            calendars      = calendars,
            inception_date = config.inception_date,
        )

        # ── CREATE EMPTY EVENT FILES ──────────────────────────────
        event_columns = [
            "portfolio", "method", "source", "tradedate", "settledate",
            "kdbegin", "kdend", "investment", "payment_currency", "tdate_fx",
            "location", "strategy", "quantity", "price", "notional",
            "original_face", "total_amount", "total_amount_base", "tranid",
            "transaction", "accrued_local", "accrued_book", "new_shares",
            "old_shares", "per_share", "legin", "legout",
            "allocation_entities", "allocation_percents", "financial_account",
            "buy_currency", "sell_currency", "buy_amt", "sell_amt",
            "feeder", "put_call", "mark_price", "mark_fx",
            "per_100FV_accrual", "per_100FV_amort", "closing_method",
            "reversal_of", "correction_reason",
        ]

        for fname in [f"{portfolio_id}.csv", f"{portfolio_id}_marks.csv"]:
            path = portfolio_dir / "Events" / fname
            with open(path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=event_columns).writeheader()

        # ── CREATE EMPTY PORTFOLIO IM ─────────────────────────────
        im_columns = [
            "investment", "ticker", "full_name", "investment_type",
            "tradedate", "kdbegin", "kdend", "asset_class", "currency",
            "is_currency", "country", "beta", "analyst", "sector",
            "industry", "contract_size", "pricing_factor",
            "underlying", "put_call", "strike",
        ]
        im_path = portfolio_dir / "RefData" / "investment_master.csv"
        with open(im_path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=im_columns).writeheader()

        print(f">>> PORTFOLIO CREATED | {portfolio_id}")

        return {
            "status":       "created",
            "portfolio_id": portfolio_id,
            "path":         str(portfolio_dir),
            "calendars":    calendar_results,
            "config":       config_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.get("/portfolio/{portfolio_id}")
def get_portfolio(portfolio_id: str):
    try:
        config = get_portfolio_config(portfolio_id)
        today  = datetime.now().strftime("%Y-%m-%d")
        config["current"] = {
            "closing_method": get_method_as_of(config.get("closing_method_history", []), today),
            "accrual_method": get_method_as_of(config.get("accrual_method_history", []), today),
            "amort_method":   get_method_as_of(config.get("amort_method_history", []), today),
        }
        return config
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.get("/portfolios")
def list_portfolios():
    try:
        funds_dir  = Path(FUNDS_PATH)
        portfolios = []
        today      = datetime.now().strftime("%Y-%m-%d")

        for d in sorted(funds_dir.iterdir()):
            if not d.is_dir():
                continue
            config_path = d / "portfolio.json"
            if not config_path.exists():
                continue
            with open(config_path) as f:
                config = json.load(f)

            portfolios.append({
                "portfolio_id":     config.get("portfolio_id"),
                "description":      config.get("description"),
                "base_currency":    config.get("base_currency"),
                "domicile_country": config.get("domicile_country"),
                "inception_date":   config.get("inception_date"),
                "managers":         config.get("managers", []),
                "status":           config.get("status"),
                "created_at":       config.get("created_at"),
                "closing_method":   get_method_as_of(config.get("closing_method_history", []), today),
                "accrual_method":   get_method_as_of(config.get("accrual_method_history", []), today),
                "amort_method":     get_method_as_of(config.get("amort_method_history", []), today),
            })

        return {"portfolios": portfolios, "count": len(portfolios)}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.post("/portfolio/{portfolio_id}/method")
def update_method(
    portfolio_id:   str,
    method_type:    str = Query(...),
    value:          str = Query(...),
    effective_from: str = Query(...),
):
    try:
        valid_types = {"closing_method", "accrual_method", "amort_method"}
        if method_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"method_type must be one of: {sorted(valid_types)}")

        config      = get_portfolio_config(portfolio_id)
        history_key = f"{method_type}_history"

        if history_key not in config:
            config[history_key] = []

        if effective_from < config.get("inception_date", ""):
            raise HTTPException(
                status_code=400,
                detail=f"effective_from cannot be before inception_date ({config.get('inception_date')})"
            )

        config[history_key].append({"value": value, "effective_from": effective_from})
        config[history_key].sort(key=lambda h: h["effective_from"])
        save_portfolio_config(portfolio_id, config)

        print(f">>> METHOD UPDATED | {portfolio_id} | {method_type}={value} from {effective_from}")

        return {
            "status": "updated", "portfolio_id": portfolio_id,
            "method_type": method_type, "value": value,
            "effective_from": effective_from, "history": config[history_key],
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# INVESTMENT ENDPOINTS
# ============================================================

@ops_router.post("/portfolio/{portfolio_id}/investment")
def add_investment(portfolio_id: str, investment: InvestmentRecord):
    try:
        portfolio_dir = Path(FUNDS_PATH) / portfolio_id

        if not portfolio_dir.exists():
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

        im_path = portfolio_dir / "RefData" / "investment_master.csv"

        existing   = {}
        fieldnames = None
        if im_path.exists():
            with open(im_path, newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                for row in reader:
                    existing[row["investment"]] = row

        if investment.investment in existing:
            raise HTTPException(
                status_code=409,
                detail=f"Investment '{investment.investment}' already exists in {portfolio_id}"
            )

        now = datetime.now().strftime("%m/%d/%Y:%H:%M:%S")
        record = {
            "investment":      investment.investment,
            "ticker":          investment.investment,
            "full_name":       investment.full_name or investment.investment,
            "investment_type": investment.investment_type,
            "tradedate":       now,
            "kdbegin":         now,
            "kdend":           "12/31/2099:00:00:00",
            "asset_class":     investment.asset_class or investment.investment_type,
            "currency":        investment.currency,
            "is_currency":     1 if investment.is_currency else 0,
            "country":         investment.country or "",
            "beta":            "",
            "analyst":         investment.analyst or "",
            "sector":          investment.sector or "",
            "industry":        investment.sector or "",
            "contract_size":   investment.contract_size,
            "pricing_factor":  investment.pricing_factor,
            "underlying":      investment.underlying or "",
            "put_call":        investment.put_call or "",
            "strike":          investment.strike or "",
        }

        cols      = list(record.keys())
        write_hdr = not im_path.exists() or os.path.getsize(im_path) == 0

        with open(im_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            if write_hdr:
                writer.writeheader()
            writer.writerow(record)

        global_im = Path(REFDATA_PATH) / "investment_master.csv"
        if global_im.exists():
            global_existing = set()
            with open(global_im, newline="") as f:
                for row in csv.DictReader(f):
                    global_existing.add(row.get("investment", ""))
            if investment.investment not in global_existing:
                with open(global_im, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=cols)
                    writer.writerow(record)

        print(f">>> INVESTMENT ADDED | {portfolio_id} | {investment.investment}")

        return {
            "status": "added", "portfolio_id": portfolio_id,
            "investment": investment.investment, "record": record,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.get("/portfolio/{portfolio_id}/investments")
def list_investments(portfolio_id: str):
    try:
        im_path = Path(FUNDS_PATH) / portfolio_id / "RefData" / "investment_master.csv"
        if not im_path.exists():
            return {"investments": [], "count": 0}
        investments = []
        with open(im_path, newline="") as f:
            for row in csv.DictReader(f):
                investments.append(dict(row))
        return {"investments": investments, "count": len(investments)}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# EVENT ENDPOINTS
# ============================================================

@ops_router.post("/portfolio/{portfolio_id}/event")
def add_event(portfolio_id: str, event: EventRecord):
    """
    Add a single event to the portfolio's event file.
    closing_method is stamped from portfolio config as of trade date.
    """
    try:
        portfolio_dir = Path(FUNDS_PATH) / portfolio_id

        if not portfolio_dir.exists():
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

        config       = get_portfolio_config(portfolio_id)
        trade_date   = _csv_date_to_ymd(event.tradedate)
        closing_meth = get_method_as_of(config.get("closing_method_history", []), trade_date) or "FIFO"

        is_mark     = event.method == "mark_prices"
        events_file = portfolio_dir / "Events" / (
            f"{portfolio_id}_marks.csv" if is_mark else f"{portfolio_id}.csv"
        )

        tranid      = _next_tranid(portfolio_dir)
        transaction = _method_to_transaction(event.method)

        row = {
            "portfolio":         portfolio_id,
            "method":            event.method,
            "source":            event.source,
            "tradedate":         event.tradedate,
            "settledate":        event.settledate,
            "kdbegin":           event.kdbegin,
            "kdend":             event.kdend,
            "investment":        event.investment,
            "payment_currency":  event.payment_currency,
            "tdate_fx":          0,
            "location":          event.location,
            "strategy":          event.strategy,
            "quantity":          event.quantity,
            "price":             event.price,
            "notional":          event.notional,
            "original_face":     event.original_face,
            "total_amount":      event.total_amount,
            "total_amount_base": event.total_amount_base,
            "tranid":            tranid,
            "transaction":       transaction,
            "accrued_local":     event.accrued_local,
            "accrued_book":      event.accrued_book,
            "new_shares":        event.new_shares,
            "old_shares":        event.old_shares,
            "per_share":         event.per_share,
            "legin":             "",
            "legout":            "",
            "allocation_entities": "",
            "allocation_percents": "",
            "financial_account": event.financial_account or "",
            "buy_currency":      event.buy_currency or "",
            "sell_currency":     event.sell_currency or "",
            "buy_amt":           event.buy_amt,
            "sell_amt":          event.sell_amt,
            "feeder":            "",
            "put_call":          "",
            "mark_price":        event.mark_price,
            "mark_fx":           event.mark_fx,
            "per_100FV_accrual": 0,
            "per_100FV_amort":   0,
            "closing_method":    closing_meth,
            "reversal_of":       "",
            "correction_reason": "",
        }

        fieldnames = list(row.keys())
        write_hdr  = not events_file.exists() or os.path.getsize(events_file) == 0

        with open(events_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_hdr:
                writer.writeheader()
            writer.writerow(row)

        # Clear event cache so next process picks up fresh
        _clear_event_cache(portfolio_id)

        print(f">>> EVENT ADDED | {portfolio_id} | {event.method} | "
              f"{event.investment} | tranid={tranid} | method={closing_meth}")

        return {
            "status":         "added",
            "portfolio_id":   portfolio_id,
            "method":         event.method,
            "investment":     event.investment,
            "tranid":         tranid,
            "closing_method": closing_meth,
            "file":           "marks" if is_mark else "events",
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.get("/portfolio/{portfolio_id}/events")
def list_events(
    portfolio_id: str,
    investment:   Optional[str] = Query(None),
    method:       Optional[str] = Query(None),
    show_reversed: bool         = Query(False, description="Include reversed events"),
    limit:        int           = Query(100, ge=1, le=10000),
):
    """List events. By default hides reversed events (kdend != 12/31/2099)."""
    try:
        events_file = Path(FUNDS_PATH) / portfolio_id / "Events" / f"{portfolio_id}.csv"
        if not events_file.exists():
            return {"events": [], "count": 0}

        events = []
        with open(events_file, newline="") as f:
            for row in csv.DictReader(f):
                if investment and row.get("investment") != investment:
                    continue
                if method and row.get("method") != method:
                    continue
                # Hide reversed events unless explicitly requested
                if not show_reversed and row.get("kdend", "12/31/2099:00:00:00") != "12/31/2099:00:00:00":
                    continue
                events.append(dict(row))
                if len(events) >= limit:
                    break

        return {"events": events, "count": len(events)}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# REVERSE EVENT
# ============================================================

@ops_router.post("/portfolio/{portfolio_id}/event/reverse")
def reverse_event(portfolio_id: str, req: ReverseRequest):
    """
    ## Reverse Event

    Stamps kdend on the target event with the current timestamp.
    The event ceases to exist from this point forward.
    The original record is preserved — never deleted.

    To rebook: call this endpoint then add a new corrected event.
    The new event should reference reversal_of = original tranid.
    """
    try:
        portfolio_dir = Path(FUNDS_PATH) / portfolio_id
        if not portfolio_dir.exists():
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

        events_file = portfolio_dir / "Events" / f"{portfolio_id}.csv"
        if not events_file.exists():
            raise HTTPException(status_code=404, detail="Events file not found")

        now_stamp = datetime.now().strftime("%m/%d/%Y:%H:%M:%S")

        # Read all rows, find and stamp the target
        rows      = []
        found     = False
        original  = None
        fieldnames = None

        with open(events_file, newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                if int(row.get("tranid", 0)) == req.tranid:
                    if row.get("kdend", "12/31/2099:00:00:00") != "12/31/2099:00:00:00":
                        raise HTTPException(
                            status_code=409,
                            detail=f"Event tranid={req.tranid} is already reversed"
                        )
                    original = dict(row)
                    row["kdend"]             = now_stamp
                    row["correction_reason"] = req.reason or "Reversed"
                    found = True
                rows.append(row)

        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"Event tranid={req.tranid} not found in {portfolio_id}"
            )

        # Ensure new columns exist in fieldnames
        for col in ["reversal_of", "correction_reason"]:
            if col not in fieldnames:
                fieldnames.append(col)

        # Write back
        with open(events_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        # Clear event cache
        _clear_event_cache(portfolio_id)

        print(f">>> EVENT REVERSED | {portfolio_id} | tranid={req.tranid} | "
              f"by={req.actor} | reason={req.reason}")

        return {
            "status":      "reversed",
            "portfolio_id": portfolio_id,
            "tranid":       req.tranid,
            "kdend":        now_stamp,
            "reason":       req.reason,
            "actor":        req.actor,
            "original":     original,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# MODIFY EVENT (REVERSE + REBOOK)
# ============================================================

@ops_router.post("/portfolio/{portfolio_id}/event/modify")
def modify_event(portfolio_id: str, req: ModifyRequest):
    """
    ## Modify Event — Temporal Correction

    Reverses the original event and creates a corrected replacement.

    Steps:
      1. Stamp kdend on original = now
      2. Write new corrected record with kdbegin = now + 1 second
         and reversal_of = original tranid
      3. Clear event cache

    Only supply the fields that changed in the request.
    All other fields are carried forward from the original.
    """
    try:
        if not req.reason or not req.reason.strip():
            raise HTTPException(status_code=400, detail="Correction reason is required")

        portfolio_dir = Path(FUNDS_PATH) / portfolio_id
        if not portfolio_dir.exists():
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

        events_file = portfolio_dir / "Events" / f"{portfolio_id}.csv"
        if not events_file.exists():
            raise HTTPException(status_code=404, detail="Events file not found")

        now          = datetime.now()
        now_stamp    = now.strftime("%m/%d/%Y:%H:%M:%S")
        new_kdbegin  = (now + timedelta(seconds=1)).strftime("%m/%d/%Y:%H:%M:%S")

        rows       = []
        found      = False
        original   = None
        fieldnames = None

        with open(events_file, newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            for row in reader:
                if int(row.get("tranid", 0)) == req.tranid:
                    if row.get("kdend", "12/31/2099:00:00:00") != "12/31/2099:00:00:00":
                        raise HTTPException(
                            status_code=409,
                            detail=f"Event tranid={req.tranid} is already reversed — rebook directly"
                        )
                    original = dict(row)
                    # Stamp the original closed
                    row["kdend"]             = now_stamp
                    row["correction_reason"] = req.reason
                    found = True
                rows.append(row)

        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"Event tranid={req.tranid} not found in {portfolio_id}"
            )

        # Ensure correction columns exist
        for col in ["reversal_of", "correction_reason"]:
            if col not in fieldnames:
                fieldnames.append(col)

        # Build corrected record — start from original, apply changes
        config       = get_portfolio_config(portfolio_id)
        new_tranid   = _next_tranid(portfolio_dir) + 1  # +1 for the write about to happen

        corrected = dict(original)
        corrected["kdbegin"]          = new_kdbegin
        corrected["kdend"]            = "12/31/2099:00:00:00"
        corrected["tranid"]           = new_tranid
        corrected["source"]           = "correction"
        corrected["reversal_of"]      = str(req.tranid)
        corrected["correction_reason"] = req.reason

        # Apply only the fields the user changed
        modifiable = [
            "method", "investment", "tradedate", "settledate", "payment_currency",
            "location", "strategy", "quantity", "price", "notional", "original_face",
            "total_amount", "total_amount_base", "accrued_local", "accrued_book",
            "buy_currency", "sell_currency", "buy_amt", "sell_amt",
            "per_share", "new_shares", "old_shares", "financial_account",
        ]
        for field in modifiable:
            val = getattr(req, field, None)
            if val is not None:
                corrected[field] = val

        # Re-stamp closing method from config as of (possibly new) trade date
        trade_date   = _csv_date_to_ymd(corrected.get("tradedate", ""))
        closing_meth = get_method_as_of(
            config.get("closing_method_history", []), trade_date
        ) or "FIFO"
        corrected["closing_method"] = closing_meth
        corrected["transaction"]    = _method_to_transaction(corrected.get("method", ""))

        rows.append(corrected)

        # Write back
        with open(events_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        # Clear event cache
        _clear_event_cache(portfolio_id)

        print(f">>> EVENT MODIFIED | {portfolio_id} | "
              f"original={req.tranid} → correction={new_tranid} | "
              f"by={req.actor} | reason={req.reason}")

        return {
            "status":           "modified",
            "portfolio_id":     portfolio_id,
            "original_tranid":  req.tranid,
            "correction_tranid": new_tranid,
            "reason":           req.reason,
            "actor":            req.actor,
            "original":         original,
            "corrected":        corrected,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GET SINGLE EVENT (for pre-population in UI)
# ============================================================

@ops_router.get("/portfolio/{portfolio_id}/event/{tranid}")
def get_event(portfolio_id: str, tranid: int):
    """Retrieve a single event by tranid for display or pre-population."""
    try:
        events_file = Path(FUNDS_PATH) / portfolio_id / "Events" / f"{portfolio_id}.csv"
        if not events_file.exists():
            raise HTTPException(status_code=404, detail="Events file not found")

        with open(events_file, newline="") as f:
            for row in csv.DictReader(f):
                if int(row.get("tranid", 0)) == tranid:
                    return {"event": dict(row)}

        raise HTTPException(status_code=404, detail=f"Event tranid={tranid} not found")

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# VIEW CORRECTIONS (reverse/rebook pairs)
# ============================================================

@ops_router.get("/portfolio/{portfolio_id}/corrections")
def list_corrections(
    portfolio_id: str,
    investment:   Optional[str] = Query(None),
    limit:        int           = Query(100, ge=1, le=10000),
):
    """
    Return correction pairs — reversed events linked with their replacements.
    Shows accountants the full correction audit trail.
    """
    try:
        events_file = Path(FUNDS_PATH) / portfolio_id / "Events" / f"{portfolio_id}.csv"
        if not events_file.exists():
            return {"corrections": [], "count": 0}

        all_rows = []
        with open(events_file, newline="") as f:
            for row in csv.DictReader(f):
                all_rows.append(dict(row))

        # Index by tranid
        by_tranid = {int(r.get("tranid", 0)): r for r in all_rows}

        # Find reversed events (kdend != 12/31/2099) and their corrections
        corrections = []
        seen = set()

        for row in all_rows:
            tranid = int(row.get("tranid", 0))
            reversal_of = row.get("reversal_of", "").strip()

            # This is a correction record pointing back to original
            if reversal_of and reversal_of.isdigit():
                orig_tranid = int(reversal_of)
                if orig_tranid in seen:
                    continue
                seen.add(orig_tranid)

                original = by_tranid.get(orig_tranid, {})
                if investment and original.get("investment") != investment:
                    continue

                corrections.append({
                    "type":       "modify",
                    "original":   original,
                    "correction": row,
                    "reason":     row.get("correction_reason", ""),
                    "reversed_at": original.get("kdend", ""),
                })

            # Reversed with no replacement (pure reversal)
            elif row.get("kdend", "12/31/2099:00:00:00") != "12/31/2099:00:00:00":
                if tranid in seen:
                    continue
                # Check no correction record points back to this
                has_correction = any(
                    r.get("reversal_of", "") == str(tranid)
                    for r in all_rows
                )
                if has_correction:
                    continue  # already handled above
                seen.add(tranid)

                if investment and row.get("investment") != investment:
                    continue

                corrections.append({
                    "type":       "reversal",
                    "original":   row,
                    "correction": None,
                    "reason":     row.get("correction_reason", ""),
                    "reversed_at": row.get("kdend", ""),
                })

            if len(corrections) >= limit:
                break

        return {"corrections": corrections, "count": len(corrections)}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# JE VIEWER
# ============================================================

@ops_router.get("/portfolio/{portfolio_id}/je")
def get_journal_entries(
    portfolio_id: str,
    calendar:     str           = Query("Monthly"),
    tranid:       Optional[int] = Query(None, description="Filter by tranid. Omit to return all."),
    limit:        int           = Query(1000, ge=1, le=50000),
):
    """
    ## Journal Entries

    Returns raw journal entries from Journals PKL files.
    Filter by tranid or omit to return all entries up to limit.
    Reads exactly as the kernel wrote them — no computation, no FIG.
    """
    import pickle

    try:
        journals_dir = (
            Path(FUNDS_PATH) / portfolio_id / "Calendars" / calendar / "Journals"
        )

        if not journals_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Journals folder not found for {portfolio_id}/{calendar}. "
                       f"Has this portfolio been processed?"
            )

        pkl_files = sorted(journals_dir.glob("*.pkl"))
        if not pkl_files:
            raise HTTPException(
                status_code=404,
                detail=f"No journal files found in {portfolio_id}/{calendar}/Journals"
            )

        matching = []

        for pkl_file in pkl_files:
            try:
                with open(pkl_file, "rb") as f:
                    journal_entries = pickle.load(f)

                for je in journal_entries:
                    if tranid is None or getattr(je, "tranid", None) == tranid:
                        matching.append(_je_to_dict(je))
                    if len(matching) >= limit:
                        break

            except Exception as e:
                print(f"    WARNING: Could not read {pkl_file.name}: {e}")
                continue

            if len(matching) >= limit:
                break

        # Sort by ibor_date then entry_type
        matching.sort(key=lambda x: (
            str(x.get("ibor_date") or ""),
            str(x.get("entry_type") or "")
        ))

        return {
            "portfolio": portfolio_id,
            "calendar":  calendar,
            "tranid":    tranid,
            "je_count":  len(matching),
            "entries":   matching,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _je_to_dict(je) -> dict:
    """Convert a JE object to a serializable dict using the class's own to_dict method."""
    try:
        return je.to_dict()
    except Exception:
        # Fallback to getattr if to_dict unavailable
        def _safe(val):
            if val is None:
                return None
            if hasattr(val, "isoformat"):
                return val.isoformat()[:10]
            return val
        return {
            "tranid":            getattr(je, "tranid",            None),
            "transaction":       getattr(je, "transaction",       None),
            "entry_type":        getattr(je, "entry_type",        None),
            "portfolio":         getattr(je, "portfolio",         None),
            "investment":        getattr(je, "investment",        None),
            "lotid":             _safe(getattr(je, "lotid",       None)),
            "tax_date":          _safe(getattr(je, "tax_date",    None)),
            "ibor_date":         _safe(getattr(je, "ibor_date",   None)),
            "tradedate":         _safe(getattr(je, "tradedate",   None)),
            "settledate":        _safe(getattr(je, "settledate",  None)),
            "ls":                getattr(je, "ls",                None),
            "location":          getattr(je, "location",          None),
            "financial_account": getattr(je, "financial_account", None),
            "quantity":          getattr(je, "quantity",          None),
            "local":             getattr(je, "local",             None),
            "book":              getattr(je, "book",              None),
            "notional":          getattr(je, "notional",          None),
            "oface":             getattr(je, "oface",             None),
            "feeder":            getattr(je, "feeder",            None),
        }


# ============================================================
# HELPERS
# ============================================================

def _clear_event_cache(portfolio_id: str) -> None:
    """Clear the process_portfolio event cache for this portfolio."""
    try:
        from process_portfolio import clear_event_cache
        clear_event_cache(portfolio_id)
        print(f">>> EVENT CACHE CLEARED via ops_routes | {portfolio_id}")
    except Exception as e:
        print(f">>> EVENT CACHE CLEAR FAILED | {portfolio_id} | {e}")


def _next_tranid(portfolio_dir: Path) -> int:
    """Generate next transaction ID."""
    tranid = 1
    for fname in [
        portfolio_dir / "Events" / f"{portfolio_dir.name}.csv",
        portfolio_dir / "Events" / f"{portfolio_dir.name}_marks.csv",
    ]:
        if fname.exists():
            with open(fname, newline="") as f:
                tranid += sum(1 for _ in csv.DictReader(f))
    return tranid


def _csv_date_to_ymd(csv_date: str) -> str:
    try:
        dt = datetime.strptime(
            csv_date.split(":")[0] + ":" +
            csv_date.split(":")[1] + ":" +
            csv_date.split(":")[2],
            "%m/%d/%Y"
        )
        return dt.strftime("%Y-%m-%d")
    except Exception:
        try:
            datetime.strptime(csv_date[:10], "%Y-%m-%d")
            return csv_date[:10]
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")


def _method_to_transaction(method: str) -> str:
    mapping = {
        "buy_equity":         "EquityPurchase",
        "sell_equity":        "EquitySale",
        "short_equity":       "EquityShort",
        "cover_equity":       "EquityCover",
        "buy_bond":           "BondPurchase",
        "sell_bond":          "BondSale",
        "buy_future":         "FuturePurchase",
        "sell_future":        "FutureSale",
        "short_future":       "FutureShort",
        "cover_future":       "FutureCover",
        "buy_option":         "OptionPurchase",
        "sell_option":        "OptionSale",
        "short_option":       "OptionShort",
        "cover_option":       "OptionCover",
        "deposit_currency":   "CurrencyDeposit",
        "withdraw_currency":  "CurrencyWithdrawal",
        "spot_fx":            "SpotFX",
        "dividend_equity":    "DividendEquity",
        "bond_coupon":        "BondCoupon",
        "split_equity":       "StockSplit",
        "mark_prices":        "PriceMark",
        "expense":            "Expense",
        "allocate":           "Allocation",
    }
    return mapping.get(method, method)