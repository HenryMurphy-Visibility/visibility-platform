# ============================================================
# ops_routes.py
# Visibility — Operations REST API Routes
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
# Module level -- above the class, alongside CALENDAR_PRESETS
ACCRUAL_METHODS = {"single_day_factor", "multiday_preceding", "multiday_following"}


class PortfolioConfig(BaseModel):
    portfolio_id: str
    base_currency: str = "USD"
    domicile_country: str = "US"
    primary_benchmark: str = "SPX"
    inception_date: str
    managers: List[str] = []
    description: Optional[str] = None
    closing_method: str = "FIFO"
    accrual_method: str = "accrue_eod"
    amort_method: str = "straight_line"
    calendars: List[str] = ["Monthly"]
    calendar_preset: Optional[str] = None
    # NEW -- explicit boundary for "what came before the first period."
    # Full date+time, user-settable. If omitted at creation, falls back
    # to inception_date with implied 00:00:00 (see get_start_period_boundary
    # below) -- not silently invented elsewhere downstream.
    start_period_boundary: Optional[str] = None

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
    tradedate:         str
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
# EVENT SCHEMA — single source of truth
# ============================================================

EVENT_COLUMNS = [
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
]


# ============================================================
# TEMPORAL METHOD HELPER
# ============================================================

def get_method_as_of(history: list, as_of_date: str) -> Optional[str]:
    if not history:
        return None
    applicable = [h for h in history if h.get("effective_from", "") <= as_of_date]
    if not applicable:
        return history[0]["value"]
    return applicable[-1]["value"]


def get_portfolio_config(portfolio_id: str) -> dict:
    config_path = Path(FUNDS_PATH) / portfolio_id / "portfolio.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")
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
    try:
        portfolio_id = config.portfolio_id.strip()
        if not portfolio_id:
            raise HTTPException(status_code=400, detail="portfolio_id is required")
        if not config.inception_date:
            raise HTTPException(status_code=400, detail="inception_date is required")

        accrual_method = (config.accrual_method or "single_day_factor").strip()
        if accrual_method not in ACCRUAL_METHODS:
            raise HTTPException(
                status_code=400,
                detail=f"accrual_method must be one of "
                       f"{sorted(ACCRUAL_METHODS)}, got '{accrual_method}'")

        portfolio_dir = Path(FUNDS_PATH) / portfolio_id
        if portfolio_dir.exists():
            raise HTTPException(status_code=409, detail=f"Portfolio '{portfolio_id}' already exists")

        for d in [portfolio_dir, portfolio_dir / "Candidates", portfolio_dir / "Events",
                  portfolio_dir / "RefData", portfolio_dir / "Calendars"]:
            d.mkdir(parents=True, exist_ok=True)

        calendars = config.calendars
        if config.calendar_preset and config.calendar_preset in CALENDAR_PRESETS:
            calendars = CALENDAR_PRESETS[config.calendar_preset]
        if not calendars:
            calendars = ["Monthly"]

        config_data = {
            "portfolio_id": portfolio_id,
            "base_currency": config.base_currency,
            "domicile_country": config.domicile_country,
            "inception_date": config.inception_date,
            "start_period_boundary": (
                    config.start_period_boundary
                    or f"{config.inception_date}T00:00:00"
            ),
            "primary_benchmark": config.primary_benchmark,
            "managers": config.managers,
            "description": config.description,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "calendars": calendars,
            "closing_method_history": [{"value": config.closing_method, "effective_from": config.inception_date}],
            "accrual_method_history": [{"value": accrual_method, "effective_from": config.inception_date}],
            "_accrual_method_choices": {
                "single_day_factor": "Each calendar day posts dated itself; "
                                     "weekends and holidays identical to "
                                     "business days. ICI emerging practice. "
                                     "Default.",
                "multiday_preceding": "Non-business days post as one entry "
                                      "dated the preceding business day "
                                      "(Friday carries Fri+Sat+Sun). ICI "
                                      "Practice 1, most common variant.",
                "multiday_following": "Non-business days post as one entry "
                                      "dated the following business day "
                                      "(Monday carries Sat+Sun+Mon). ICI "
                                      "Practice 1, less common variant.",
            },
            "amort_method_history": [{"value": config.amort_method, "effective_from": config.inception_date}],
        }

        with open(portfolio_dir / "portfolio.json", "w") as f:
            json.dump(config_data, f, indent=2)

        calendar_results = generate_calendars(
            portfolio=portfolio_id, calendars=calendars, inception_date=config.inception_date
        )

        for fname in [f"{portfolio_id}.csv", f"{portfolio_id}_marks.csv"]:
            with open(portfolio_dir / "Events" / fname, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=EVENT_COLUMNS).writeheader()

        im_columns = [
            "investment", "ticker", "full_name", "investment_type",
            "tradedate", "kdbegin", "kdend", "asset_class", "currency",
            "is_currency", "country", "beta", "analyst", "sector",
            "industry", "contract_size", "pricing_factor",
            "underlying", "put_call", "strike",
        ]
        with open(portfolio_dir / "RefData" / "investment_master.csv", "w", newline="") as f:
            csv.DictWriter(f, fieldnames=im_columns).writeheader()

        print(f">>> PORTFOLIO CREATED | {portfolio_id} | accrual={accrual_method}")
        return {"status": "created", "portfolio_id": portfolio_id,
                "path": str(portfolio_dir), "calendars": calendar_results, "config": config_data}

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


def get_start_period_boundary(portfolio_config: dict) -> Optional[str]:
    """
    Return the explicit start_period_boundary for a portfolio, with the
    confirmed fallback for portfolios created before this field existed:
    inception_date + implied 00:00:00.

    Returns None only if even inception_date is missing (should not
    happen for any valid portfolio.json).

    This is a READ-time fallback, not a write-time one -- existing
    portfolios are not silently rewritten; every read of an old
    portfolio.json computes the same fallback consistently, until/unless
    the portfolio is explicitly updated with a real value.
    """
    explicit = portfolio_config.get("start_period_boundary")
    if explicit:
        return explicit
    inception = portfolio_config.get("inception_date")
    if not inception:
        return None
    return f"{inception}T00:00:00"

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
                "inception_date": config.get("inception_date"),
                "primary_benchmark": config.get("primary_benchmark", "SPX"),
                "managers": config.get("managers", []),
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
def update_method(portfolio_id: str, method_type: str = Query(...),
                  value: str = Query(...), effective_from: str = Query(...)):
    try:
        valid_types = {"closing_method", "accrual_method", "amort_method"}
        if method_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"method_type must be one of: {sorted(valid_types)}")
        config      = get_portfolio_config(portfolio_id)
        history_key = f"{method_type}_history"
        if history_key not in config:
            config[history_key] = []
        if effective_from < config.get("inception_date", ""):
            raise HTTPException(status_code=400,
                detail=f"effective_from cannot be before inception_date ({config.get('inception_date')})")
        config[history_key].append({"value": value, "effective_from": effective_from})
        config[history_key].sort(key=lambda h: h["effective_from"])
        save_portfolio_config(portfolio_id, config)
        return {"status": "updated", "portfolio_id": portfolio_id,
                "method_type": method_type, "value": value,
                "effective_from": effective_from, "history": config[history_key]}
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
        existing = {}
        if im_path.exists():
            with open(im_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing[row["investment"]] = row

        if investment.investment in existing:
            raise HTTPException(status_code=409,
                detail=f"Investment '{investment.investment}' already exists in {portfolio_id}")

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
                    csv.DictWriter(f, fieldnames=cols).writerow(record)

        print(f">>> INVESTMENT ADDED | {portfolio_id} | {investment.investment}")
        return {"status": "added", "portfolio_id": portfolio_id,
                "investment": investment.investment, "record": record}

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
    try:
        portfolio_dir = Path(FUNDS_PATH) / portfolio_id
        if not portfolio_dir.exists():
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

        from validation_engine    import validate_event as _validate_event
        from validation_functions import csv_date_to_iso
        from v_config             import REFDATA_PATH

        config    = get_portfolio_config(portfolio_id)
        im_record = _get_im_record(portfolio_id, event.investment)

        report = _validate_event(
            method  = event.method,
            payload = {
                "portfolio":         portfolio_id,
                "method":            event.method,
                "investment":        event.investment,
                "tradedate":         csv_date_to_iso(event.tradedate),
                "settledate":        csv_date_to_iso(event.settledate),
                "quantity":          event.quantity,
                "price":             event.price,
                "notional":          event.notional,
                "total_amount":      event.total_amount,
                "total_amount_base": event.total_amount_base,
                "accrued_local":     event.accrued_local,
                "accrued_book":      event.accrued_book,
                "per_share":         event.per_share,
                "new_shares":        event.new_shares,
                "old_shares":        event.old_shares,
                "buy_currency":      event.buy_currency,
                "sell_currency":     event.sell_currency,
                "buy_amt":           event.buy_amt,
                "sell_amt":          event.sell_amt,
                "payment_currency":  event.payment_currency,
                "pricing_factor":    float(im_record.get("pricing_factor", 1) or 1),
                "contract_size":     float(im_record.get("contract_size",  0) or 0),
            },
            context = {
                "im_record":       im_record,
                "investment_type": im_record.get("investment_type", ""),
                "base_currency":   config.get("base_currency", "USD"),
                "refdata_path":    str(REFDATA_PATH),
            },
            line = 1
        )

        if report.has_errors:
            raise HTTPException(status_code=400, detail=report.first_error)

        if report.has_warnings:
            print(f">>> LINE1 WARNINGS | {portfolio_id} | {event.method} | {report.summary}")

        is_future = event.method in {
            "buy_future", "sell_future", "short_future", "cover_future"
        }
        final_total_amount      = event.total_amount
        final_total_amount_base = event.total_amount_base
        final_notional          = event.notional

        if report.computed:
            if not is_future:
                if report.computed.get("total_amount"):
                    final_total_amount = report.computed["total_amount"]
                if report.computed.get("total_amount_base"):
                    final_total_amount_base = report.computed["total_amount_base"]
            else:
                if report.computed.get("notional"):
                    final_notional          = report.computed["notional"]
                    final_total_amount      = report.computed["notional"]
                    final_total_amount_base = report.computed["notional"]

        print(f">>> LINE1 OK | {portfolio_id} | {event.method} | {event.investment} "
              f"| local={final_total_amount} | base={final_total_amount_base}")

        trade_date   = _csv_date_to_ymd(event.tradedate)
        closing_meth = get_method_as_of(config.get("closing_method_history", []), trade_date) or "FIFO"
        is_mark      = event.method == "mark_prices"
        events_file  = portfolio_dir / "Events" / (
            f"{portfolio_id}_marks.csv" if is_mark else f"{portfolio_id}.csv"
        )
        tranid      = _next_tranid(portfolio_dir)
        transaction = _method_to_transaction(event.method)

        row = {
            "portfolio":           portfolio_id,
            "method":              event.method,
            "source":              event.source,
            "tradedate":           event.tradedate,
            "settledate":          event.settledate,
            "kdbegin":             event.kdbegin,
            "kdend":               event.kdend,
            "investment":          event.investment,
            "payment_currency":    event.payment_currency,
            "tdate_fx":            0,
            "location":            event.location,
            "strategy":            event.strategy,
            "quantity":            event.quantity,
            "price":               event.price,
            "notional":            final_notional,
            "original_face":       event.original_face,
            "total_amount":        final_total_amount,
            "total_amount_base":   final_total_amount_base,
            "tranid":              tranid,
            "transaction":         transaction,
            "accrued_local":       event.accrued_local,
            "accrued_book":        event.accrued_book,
            "new_shares":          event.new_shares,
            "old_shares":          event.old_shares,
            "per_share":           event.per_share,
            "legin":               "",
            "legout":              "",
            "allocation_entities": "",
            "allocation_percents": "",
            "financial_account":   event.financial_account or "",
            "buy_currency":        event.buy_currency or "",
            "sell_currency":       event.sell_currency or "",
            "buy_amt":             event.buy_amt,
            "sell_amt":            event.sell_amt,
            "feeder":              "",
            "put_call":            "",
            "mark_price":          event.mark_price,
            "mark_fx":             event.mark_fx,
            "per_100FV_accrual":   0,
            "per_100FV_amort":     0,
            "closing_method":      closing_meth,
        }

        write_hdr = not events_file.exists() or os.path.getsize(events_file) == 0
        with open(events_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=EVENT_COLUMNS)
            if write_hdr:
                writer.writeheader()
            writer.writerow(row)

        _clear_event_cache(portfolio_id)
        print(f">>> EVENT ADDED | {portfolio_id} | {event.method} | "
              f"{event.investment} | tranid={tranid}")

        return {
            "status":            "added",
            "portfolio_id":      portfolio_id,
            "method":            event.method,
            "investment":        event.investment,
            "tranid":            tranid,
            "closing_method":    closing_meth,
            "file":              "marks" if is_mark else "events",
            "total_amount":      final_total_amount,
            "total_amount_base": final_total_amount_base,
            "notional":          final_notional,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.get("/portfolio/{portfolio_id}/events")
def list_events(portfolio_id: str, investment: Optional[str] = Query(None),
                method: Optional[str] = Query(None),
                show_reversed: bool = Query(False), limit: int = Query(100, ge=1, le=10000)):
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
# MARKS VIEW ENDPOINTS — price & FX history lookups
# ============================================================

def _norm_date_iso(val: str) -> str:
    """Normalize '1/5/2026', '01/05/2026', '2026-01-05' (with optional
    ':00:00:00' / 'T..' suffix) → 'YYYY-MM-DD'. Same logic as the FX rate
    lookup, so date-range filtering actually matches the file's M/D/YYYY dates."""
    if not val:
        return ""
    val = str(val).strip()
    if "/" in val:
        parts = val.split("/")
        if len(parts) >= 3:
            m = parts[0].zfill(2)
            d = parts[1].zfill(2)
            y = parts[2].split(":")[0].split("T")[0].strip()
            return f"{y}-{m}-{d}"
    if len(val) >= 10 and val[4] == "-":
        return val[:10]
    return val


@ops_router.get("/prices")
def get_prices(ticker:    str = Query(...),
               date_from: str = Query(None),
               date_to:   str = Query(None)):
    """Price history for one ticker, optionally within a date range.
    Ticker is mandatory — the file is large and is always searched by name."""
    try:
        from v_config import REFDATA_PATH
        path = Path(REFDATA_PATH) / "price_master.csv"
        if not path.exists():
            raise HTTPException(status_code=404, detail="price_master.csv not found")

        tkr   = ticker.strip().upper()
        d_from = _norm_date_iso(date_from) if date_from else None
        d_to   = _norm_date_iso(date_to)   if date_to   else None

        rows = []
        with open(path, newline="", encoding="cp1252") as f:
            for row in csv.DictReader(f):
                if str(row.get("ticker", "")).strip().upper() != tkr:
                    continue
                iso = _norm_date_iso(row.get("date", ""))
                if d_from and iso < d_from:
                    continue
                if d_to and iso > d_to:
                    continue
                rows.append({
                    "date":     iso,
                    "ticker":   str(row.get("ticker", "")).strip(),
                    "currency": str(row.get("currency", "")).strip(),
                    "price":    row.get("price", ""),
                })

        rows.sort(key=lambda r: r["date"])
        return {"ticker": tkr, "count": len(rows), "rows": rows}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.get("/fx")
def get_fx_history(currency:  str = Query(...),
                   date_from: str = Query(None),
                   date_to:   str = Query(None)):
    """FX rate history for one currency, optionally within a date range.
    Currency is mandatory — same fast-search-by-key design as prices."""
    try:
        from v_config import REFDATA_PATH
        path = Path(REFDATA_PATH) / "fx_master.csv"
        if not path.exists():
            raise HTTPException(status_code=404, detail="fx_master.csv not found")

        ccy    = currency.strip().upper()
        d_from = _norm_date_iso(date_from) if date_from else None
        d_to   = _norm_date_iso(date_to)   if date_to   else None

        rows = []
        with open(path, newline="", encoding="cp1252") as f:
            for row in csv.DictReader(f):
                if str(row.get("currency", "")).strip().upper() != ccy:
                    continue
                iso = _norm_date_iso(row.get("date", ""))
                if d_from and iso < d_from:
                    continue
                if d_to and iso > d_to:
                    continue
                rows.append({
                    "date":     iso,
                    "currency": str(row.get("currency", "")).strip(),
                    "price":    row.get("price", ""),
                })

        rows.sort(key=lambda r: r["date"])
        return {"currency": ccy, "count": len(rows), "rows": rows}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# VALIDATE ENDPOINT
# ============================================================

@ops_router.post("/validate")
def validate_event_endpoint(portfolio_id: str = Query(...), body: dict = None):
    try:
        from validation_engine    import validate_event as _validate_event
        from validation_functions import csv_date_to_iso
        from v_config             import REFDATA_PATH

        if body is None:
            body = {}

        method     = body.get("method", "")
        investment = body.get("investment", "")
        im_record  = _get_im_record(portfolio_id, investment) if investment else {}

        try:
            config   = get_portfolio_config(portfolio_id)
            base_ccy = config.get("base_currency", "USD")
        except Exception:
            base_ccy = "USD"

        tradedate  = body.get("tradedate",  "")
        settledate = body.get("settledate", "")
        if tradedate  and "/" in tradedate:
            tradedate  = csv_date_to_iso(tradedate)
        if settledate and "/" in settledate:
            settledate = csv_date_to_iso(settledate)

        payload = {
            "portfolio":         portfolio_id,
            "method":            method,
            "investment":        investment,
            "tradedate":         tradedate,
            "settledate":        settledate,
            "quantity":          float(body.get("quantity",          0) or 0),
            "price":             float(body.get("price",             0) or 0),
            "notional":          float(body.get("notional",          0) or 0),
            "total_amount":      float(body.get("total_amount",      0) or 0),
            "total_amount_base": float(body.get("total_amount_base", 0) or 0),
            "accrued_local":     float(body.get("accrued_local",     0) or 0),
            "accrued_book":      float(body.get("accrued_book",      0) or 0),
            "per_share":         float(body.get("per_share",         0) or 0),
            "new_shares":        float(body.get("new_shares",        0) or 0),
            "old_shares":        float(body.get("old_shares",        0) or 0),
            "buy_currency":      body.get("buy_currency")  or None,
            "sell_currency":     body.get("sell_currency") or None,
            "buy_amt":           float(body.get("buy_amt",           0) or 0),
            "sell_amt":          float(body.get("sell_amt",          0) or 0),
            "payment_currency":  body.get("payment_currency", "USD"),
            "pricing_factor":    float(im_record.get("pricing_factor", 1) or 1),
            "contract_size":     float(im_record.get("contract_size",  0) or 0),
        }

        report = _validate_event(
            method  = method,
            payload = payload,
            context = {
                "im_record":       im_record,
                "investment_type": im_record.get("investment_type", ""),
                "base_currency":   base_ccy,
                "refdata_path":    str(REFDATA_PATH),
            },
            line = 1
        )

        return {
            "ok":       report.ok,
            "errors":   [{"field": f.field, "message": f.message} for f in report.errors],
            "warnings": [{"field": f.field, "message": f.message} for f in report.warnings],
            "computed": report.computed,
            "fx_rate":  payload.get("fx_rate"),
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# CALENDAR ENDPOINT
# ============================================================

@ops_router.get("/portfolio/{portfolio_id}/calendar/{calendar}")
def view_calendar(portfolio_id: str, calendar: str):
    try:
        cal_path = Path(FUNDS_PATH) / portfolio_id / "Calendars" / calendar / f"{calendar}.txt"
        if not cal_path.exists():
            raise HTTPException(status_code=404,
                detail=f"Calendar '{calendar}' not found for {portfolio_id}")

        periods = []
        with open(cal_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    periods.append({
                        "period_name":   rec.get("period_name"),
                        "status":        rec.get("period_status"),
                        "period_start":  rec.get("current_period_start"),
                        "period_cutoff": rec.get("current_period_cutoff"),
                        "knowledge":     rec.get("current_period_knowledge"),
                    })
                except Exception:
                    continue

        return {"portfolio": portfolio_id, "calendar": calendar,
                "period_count": len(periods), "periods": periods}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# FX RATE LOOKUP
# ============================================================

@ops_router.get("/fx/rate")
def get_fx_rate(currency: str = Query(...), trade_date: str = Query(...)):
    """
    Return the FX rate (USD value of one unit of `currency`) on `trade_date`.

    Response shape:
      {"rate": <float>, "found": true,  "source": "fx_master"}   normal hit
      {"rate": 1.0,     "found": true,  "source": "passthrough"} USD (rate is genuinely 1.0)
      {"rate": null,    "found": false, "source": "not_found"}   foreign rate MISSING
      {"rate": null,    "found": false, "source": "file_not_found"}

    NOTE: for a foreign currency, a missing rate returns found=false with rate=null.
    It must NOT return 1.0 — the caller treats found=false as an error and refuses
    to commit, because 1.0 for a foreign trade silently sets base = local (corruption).
    """
    try:
        from v_config import REFDATA_PATH

        # USD is a genuine 1.0 passthrough — distinct from a failed lookup.
        if currency.upper() == "USD":
            return {"rate": 1.0, "found": True, "source": "passthrough"}

        fx_path = Path(REFDATA_PATH) / "fx_master.csv"
        if not fx_path.exists():
            return {"rate": None, "found": False, "source": "file_not_found"}

        # Normalize the requested date to YYYY-MM-DD.
        td_norm = _normalize_fx_date(trade_date)

        with open(fx_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                # Column-name tolerant: date / fx_date ; currency / ticker ; price / rate / close
                raw_date = str(row.get("date") or row.get("fx_date") or "").strip()
                raw_ccy = str(row.get("currency") or row.get("ticker") or "").strip()
                raw_rate = (row.get("price") or row.get("rate") or
                            row.get("close") or "")

                if raw_ccy.upper() != currency.upper():
                    continue
                if _normalize_fx_date(raw_date) != td_norm:
                    continue

                try:
                    rate = float(raw_rate)
                except (TypeError, ValueError):
                    continue
                if rate <= 0:
                    continue

                return {"rate": rate, "found": True, "source": "fx_master"}

        # Foreign currency, no row matched — DO NOT default to 1.0.
        return {"rate": None, "found": False, "source": "not_found"}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _normalize_fx_date(val: str) -> str:
    """
    Normalize any of these to 'YYYY-MM-DD':
      '2026-01-02', '2026-01-02T00:00:00',
      '01/02/2026', '01/02/2026:00:00:00', '1/2/2026'
    Mirrors the proof engine's _norm_date so the endpoint matches the same
    rows the close process does.
    """
    if not val:
        return ""
    val = str(val).strip()
    # M/D/YYYY (optionally with a :HH:MM:SS suffix)
    if "/" in val:
        parts = val.split("/")
        if len(parts) >= 3:
            m = parts[0].zfill(2)
            d = parts[1].zfill(2)
            y = parts[2].split(":")[0].split("T")[0].strip()
            return f"{y}-{m}-{d}"
    # ISO (optionally with T or space time suffix)
    if len(val) >= 10 and val[4] == "-":
        return val[:10]
    return val

# ============================================================
# PROOF ENGINE
# ============================================================

@ops_router.post("/portfolio/{portfolio_id}/proof")
def run_proof_endpoint(
        portfolio_id: str,
        calendar: str = Query("Monthly"),
        period: Optional[str] = Query(None),
        investment: Optional[str] = Query(None),
        tranid: Optional[int] = Query(None),
        pillar: Optional[str] = Query(None),
        verbose: bool = Query(False),
):
    try:
        from proof_engine import (
            load_events, load_investment_master, load_price_index,
            load_fx_index, load_jes_from_journals, load_calendar_records,
            load_prior_accumulation, load_portfolio_config,
            pillar_availability, pillar_balance, pillar_settle_fx,
            pillar_marks, pillar_chart_of_accounts, pillar_data,
            _safe_float, BASE_CURRENCY,
        )
        from v_config import FUNDS_PATH, REFDATA_PATH

        funds_path = str(FUNDS_PATH)
        refdata_path = str(REFDATA_PATH)

        events = load_events(portfolio_id, funds_path)
        im = load_investment_master(portfolio_id, funds_path)
        price_index = load_price_index(refdata_path)
        fx_index = load_fx_index(refdata_path)
        jes_by_period, period_meta = load_jes_from_journals(portfolio_id, calendar, funds_path, period)
        calendar_records = load_calendar_records(portfolio_id, calendar, funds_path)

        portfolio_config = load_portfolio_config(portfolio_id, funds_path)
        base_currency = (portfolio_config or {}).get("base_currency") or BASE_CURRENCY

        if period:
            calendar_records = [r for r in calendar_records
                                if r.get("period_name") == period]

        if investment:
            inv_upper = investment.upper()
            events = [e for e in events
                      if e.get("investment", "").upper() == inv_upper]
        if tranid:
            events = [e for e in events
                      if int(_safe_float(e.get("tranid")) or 0) == tranid]

        # Build prior_accumulation for carry-forward
        prior_accumulation = None
        if period:
            prior_accumulation = load_prior_accumulation(
                portfolio_id, calendar, funds_path, period
            )

        run_all = pillar is None

        def _serialize(r):
            return {
                "pillar": r.pillar,
                "passes": len(r.passes),
                "warnings": len(r.warnings),
                "failures": len(r.failures),
                "all_clear": r.all_clear,
                "has_critical": r.has_critical,
                "pass_list": [i.message for i in r.passes] if verbose else [],
                "warning_list": [i.message for i in r.warnings],
                "failure_list": [i.message for i in r.failures],
                "skipped": [i.message for i in r.skipped] if verbose else [],
            }

        results = {}

        if run_all or pillar == "availability":
            results["availability"] = _serialize(
                pillar_availability(events, im, calendar_records, price_index, fx_index))

        if run_all or pillar == "balance":
            results["balance"] = _serialize(
                pillar_balance(jes_by_period))

        if run_all or pillar == "settle_fx":
            results["settle_fx"] = _serialize(
                pillar_settle_fx(events, jes_by_period, fx_index))

        if run_all or pillar == "marks":
            results["marks"] = _serialize(
                pillar_marks(events, im, calendar_records, jes_by_period,
                             price_index, fx_index, prior_accumulation))

        if run_all or pillar == "chart_of_accounts":
            results["chart_of_accounts"] = _serialize(
                pillar_chart_of_accounts(jes_by_period))

        if run_all or pillar == "data":
            results["data"] = _serialize(
                pillar_data(events, jes_by_period, im, base_currency))

        total_pass = sum(v["passes"] for v in results.values())
        total_warn = sum(v["warnings"] for v in results.values())
        total_fail = sum(v["failures"] for v in results.values())
        all_clear = all(v["all_clear"] for v in results.values())

        return {
            "portfolio": portfolio_id,
            "calendar": calendar,
            "period": period or "ALL",
            "investment": investment,
            "total_pass": total_pass,
            "total_warn": total_warn,
            "total_fail": total_fail,
            "all_clear": all_clear,
            "events_loaded": len(events),
            "periods_checked": len(jes_by_period),
            "pillars": results,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# REVERSE EVENT
# ============================================================

@ops_router.post("/portfolio/{portfolio_id}/event/reverse")
def reverse_event(portfolio_id: str, req: ReverseRequest):
    try:
        portfolio_dir = Path(FUNDS_PATH) / portfolio_id
        if not portfolio_dir.exists():
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

        events_file = portfolio_dir / "Events" / f"{portfolio_id}.csv"
        if not events_file.exists():
            raise HTTPException(status_code=404, detail="Events file not found")

        now_stamp  = datetime.now().strftime("%m/%d/%Y:%H:%M:%S")
        rows       = []
        found      = False
        original   = None
        fieldnames = None

        with open(events_file, newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                if int(row.get("tranid", 0)) == req.tranid:
                    if row.get("kdend", "12/31/2099:00:00:00") != "12/31/2099:00:00:00":
                        raise HTTPException(status_code=409,
                            detail=f"Event tranid={req.tranid} is already reversed")
                    original      = dict(row)
                    row["kdend"]  = now_stamp
                    found         = True
                rows.append(row)

        if not found:
            raise HTTPException(status_code=404,
                detail=f"Event tranid={req.tranid} not found in {portfolio_id}")

        with open(events_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        _write_audit(portfolio_id, "REVERSE", req.tranid, None, req.actor, req.reason)
        _clear_event_cache(portfolio_id)

        print(f">>> EVENT REVERSED | {portfolio_id} | tranid={req.tranid}")

        return {"status": "reversed", "portfolio_id": portfolio_id,
                "tranid": req.tranid, "kdend": now_stamp,
                "reason": req.reason, "actor": req.actor, "original": original}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# MODIFY EVENT
# ============================================================

@ops_router.post("/portfolio/{portfolio_id}/event/modify")
def modify_event(portfolio_id: str, req: ModifyRequest):
    try:
        if not req.reason or not req.reason.strip():
            raise HTTPException(status_code=400, detail="Correction reason is required")

        portfolio_dir = Path(FUNDS_PATH) / portfolio_id
        if not portfolio_dir.exists():
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

        events_file = portfolio_dir / "Events" / f"{portfolio_id}.csv"
        if not events_file.exists():
            raise HTTPException(status_code=404, detail="Events file not found")

        now         = datetime.now()
        now_stamp   = now.strftime("%m/%d/%Y:%H:%M:%S")
        new_kdbegin = (now + timedelta(seconds=1)).strftime("%m/%d/%Y:%H:%M:%S")

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
                        raise HTTPException(status_code=409,
                            detail=f"Event tranid={req.tranid} is already reversed — rebook directly")
                    original     = dict(row)
                    row["kdend"] = now_stamp
                    found        = True
                rows.append(row)

        if not found:
            raise HTTPException(status_code=404,
                detail=f"Event tranid={req.tranid} not found in {portfolio_id}")

        config     = get_portfolio_config(portfolio_id)
        new_tranid = _next_tranid(portfolio_dir) + 1

        corrected = dict(original)
        corrected["kdbegin"] = new_kdbegin
        corrected["kdend"]   = "12/31/2099:00:00:00"
        corrected["tranid"]  = new_tranid
        corrected["source"]  = "correction"

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

        trade_date = _csv_date_to_ymd(corrected.get("tradedate", ""))
        corrected["closing_method"] = get_method_as_of(
            config.get("closing_method_history", []), trade_date) or "FIFO"
        corrected["transaction"] = _method_to_transaction(corrected.get("method", ""))

        rows.append(corrected)

        with open(events_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        _write_audit(portfolio_id, "MODIFY", req.tranid, new_tranid, req.actor, req.reason)
        _clear_event_cache(portfolio_id)

        print(f">>> EVENT MODIFIED | {portfolio_id} | "
              f"original={req.tranid} → correction={new_tranid}")

        return {"status": "modified", "portfolio_id": portfolio_id,
                "original_tranid": req.tranid, "correction_tranid": new_tranid,
                "reason": req.reason, "actor": req.actor,
                "original": original, "corrected": corrected}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GET SINGLE EVENT
# ============================================================

@ops_router.get("/portfolio/{portfolio_id}/event/{tranid}")
def get_event(portfolio_id: str, tranid: int):
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
# VIEW CORRECTIONS
# ============================================================

@ops_router.get("/portfolio/{portfolio_id}/corrections")
def list_corrections(portfolio_id: str, investment: Optional[str] = Query(None),
                     limit: int = Query(100, ge=1, le=1000)):
    try:
        audit_path  = Path(FUNDS_PATH) / portfolio_id / "Events" / f"{portfolio_id}_audit.csv"
        events_file = Path(FUNDS_PATH) / portfolio_id / "Events" / f"{portfolio_id}.csv"

        if not audit_path.exists():
            return {"corrections": [], "count": 0}

        all_rows = {}
        if events_file.exists():
            with open(events_file, newline="") as f:
                for row in csv.DictReader(f):
                    all_rows[row.get("tranid", "")] = dict(row)

        corrections = []
        with open(audit_path, newline="") as f:
            for row in csv.DictReader(f):
                original_tranid = str(row.get("original_tranid", ""))
                new_tranid      = str(row.get("new_tranid", ""))
                action          = row.get("action", "")
                original        = all_rows.get(original_tranid, {})
                correction      = all_rows.get(new_tranid, {}) if new_tranid else None

                if investment and original.get("investment") != investment:
                    continue

                corrections.append({
                    "type":        "modify" if action == "MODIFY" else "reversal",
                    "original":    original,
                    "correction":  correction,
                    "reason":      row.get("reason", ""),
                    "reversed_at": row.get("timestamp", ""),
                    "actor":       row.get("actor", ""),
                })

                if len(corrections) >= limit:
                    break

        return {"corrections": corrections, "count": len(corrections)}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# BOND ACCRUAL
# ============================================================

@ops_router.get("/bond/accrual")
def get_bond_accrual(
    portfolio:   str = Query(...),
    investment:  str = Query(...),
    settle_date: str = Query(...),
):
    try:
        from bond_calc import calculate_accrued_interest as _calc_accrual

        bond_info_path = Path(FUNDS_PATH) / portfolio / "RefData" / "bond_info.csv"
        if not bond_info_path.exists():
            bond_info_path = Path(REFDATA_PATH) / "bond_info.csv"
        if not bond_info_path.exists():
            raise HTTPException(status_code=404, detail=f"Bond info not found for portfolio {portfolio}")

        bond = None
        with open(bond_info_path, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("investment", "").strip().upper() == investment.upper():
                    bond = row
                    break

        if bond is None:
            raise HTTPException(status_code=404, detail=f"Bond '{investment}' not found")

        coupon_rate       = float(bond.get("coupon_rate", 0))
        payment_frequency = bond.get("payment_frequency", "SEMI_ANNUAL")
        day_count         = bond.get("day_count_convention", "30E/360")
        fv                = float(bond.get("face_value", 100))
        semi_split        = bond.get("semi_split", "A")

        try:
            sd = datetime.strptime(settle_date, "%Y-%m-%d")
            settle_str = sd.strftime("%m/%d/%Y")
        except Exception:
            settle_str = settle_date

        result = _calc_accrual(
            issue_date           = bond.get("issue_date", ""),
            first_coupon_date    = bond.get("first_coupon_date", ""),
            maturity_date        = bond.get("maturity_date", ""),
            settlement_date      = settle_str,
            coupon_rate          = coupon_rate,
            payment_frequency    = payment_frequency,
            day_count_convention = day_count,
            face_value           = fv,
            semi_split           = semi_split,
        )

        def _fmt(d):
            return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)

        return {
            "investment":         investment,
            "settle_date":        settle_date,
            "last_coupon_date":   _fmt(result["last_coupon_date"]),
            "next_coupon_date":   _fmt(result["next_coupon_date"]),
            "days_of_accrual":    result["days_of_accrual"],
            "days_in_period":     result["days_in_period"],
            "coupon_rate_pct":    result["coupon_rate_pct"],
            "semi_annual_coupon": result["semi_annual_coupon"],
            "daily_per_100":      result["daily_per_100"],
            "accrued_per_100":    result["accrued_per_100"],
            "face_value":         fv,
            "day_count":          day_count,
            "payment_frequency":  payment_frequency,
            "note":               result.get("note", ""),
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# PORTFOLIO BOND INFO
# ============================================================

@ops_router.post("/portfolio/{portfolio_id}/bond_info")
def add_bond_info(portfolio_id: str, bond_info: dict):
    try:
        portfolio_dir  = Path(FUNDS_PATH) / portfolio_id
        if not portfolio_dir.exists():
            raise HTTPException(status_code=404, detail=f"Portfolio '{portfolio_id}' not found")

        bond_info_path = portfolio_dir / "RefData" / "bond_info.csv"
        investment     = bond_info.get("investment", "").strip()

        if not investment:
            raise HTTPException(status_code=400, detail="investment field required")

        existing   = []
        fieldnames = None
        if bond_info_path.exists():
            with open(bond_info_path, newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                for row in reader:
                    if row.get("investment", "").strip().upper() == investment.upper():
                        raise HTTPException(status_code=409,
                            detail=f"Bond info for '{investment}' already exists in {portfolio_id}")
                    existing.append(row)

        if not fieldnames:
            fieldnames = list(bond_info.keys())

        write_hdr = not bond_info_path.exists() or os.path.getsize(bond_info_path) == 0
        with open(bond_info_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if write_hdr:
                writer.writeheader()
            writer.writerow(bond_info)

        print(f">>> BOND INFO ADDED | {portfolio_id} | {investment}")
        return {"status": "added", "portfolio_id": portfolio_id, "investment": investment}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GLOBAL INVESTMENT LOOKUP
# ============================================================

@ops_router.get("/global/investment/{investment}")
def get_global_investment(investment: str):
    try:
        global_im   = Path(REFDATA_PATH) / "investment_master.csv"
        bond_info   = Path(REFDATA_PATH) / "bond_info.csv"
        im_record   = None
        bond_record = None

        if global_im.exists():
            with open(global_im, newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("investment", "").strip().upper() == investment.upper():
                        im_record = dict(row)
                        break

        if im_record and im_record.get("investment_type", "").upper() == "BOND":
            if bond_info.exists():
                with open(bond_info, newline="") as f:
                    for row in csv.DictReader(f):
                        if row.get("investment", "").strip().upper() == investment.upper():
                            bond_record = dict(row)
                            break

        if im_record:
            return {"found": True, "investment": im_record, "bond_info": bond_record}
        else:
            return {"found": False, "investment": None, "bond_info": None}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# JE VIEWER
# ============================================================

@ops_router.get("/portfolio/{portfolio_id}/je")
def get_journal_entries(portfolio_id: str,
                        calendar:          str           = Query("Monthly"),
                        tranid:            Optional[int] = Query(None),
                        period_from:       Optional[str] = Query(None),
                        period_to:         Optional[str] = Query(None),
                        entry_type:        Optional[str] = Query(None),
                        exclude_valuation: bool          = Query(False),
                        limit:             int           = Query(10000)):
    import pickle
    try:
        journals_dir = Path(FUNDS_PATH) / portfolio_id / "Calendars" / calendar / "Journals"
        if not journals_dir.exists():
            raise HTTPException(status_code=404,
                detail=f"Journals folder not found for {portfolio_id}/{calendar}.")

        pkl_files = sorted(journals_dir.glob("*.pkl"))
        if not pkl_files:
            raise HTTPException(status_code=404,
                detail=f"No journal files found in {portfolio_id}/{calendar}/Journals")

        if period_from or period_to:
            filtered = []
            for f in pkl_files:
                period_key = f.name[:7]
                if period_from and period_key < period_from:
                    continue
                if period_to and period_key > period_to:
                    continue
                filtered.append(f)
            pkl_files = filtered

        if entry_type:
            pkl_files = [f for f in pkl_files if entry_type.lower() in f.name.lower()]

        matching = []
        for pkl_file in pkl_files:
            try:
                with open(pkl_file, "rb") as f:
                    data = pickle.load(f)
                journal_entries = data.get("journals", []) if isinstance(data, dict) else data
                for je in journal_entries:
                    if tranid is not None and getattr(je, "tranid", None) != tranid:
                        continue
                    if exclude_valuation and getattr(je, "transaction", "") == "Valuation":
                        continue
                    matching.append(_je_to_dict(je))
                    if len(matching) >= limit:
                        break
            except Exception as e:
                print(f"    WARNING: Could not read {pkl_file.name}: {e}")
                continue
            if len(matching) >= limit:
                break

        matching.sort(key=lambda x: (str(x.get("ibor_date") or ""), str(x.get("entry_type") or "")))

        return {"portfolio": portfolio_id, "calendar": calendar,
                "tranid": tranid, "je_count": len(matching), "entries": matching}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _je_to_dict(je) -> dict:
    try:
        return je.to_dict()
    except Exception:
        def _safe(val):
            if val is None: return None
            if hasattr(val, "isoformat"): return val.isoformat()[:10]
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

def _get_im_record(portfolio_id: str, investment: str) -> dict:
    im_path = Path(FUNDS_PATH) / portfolio_id / "RefData" / "investment_master.csv"
    if not im_path.exists():
        return {}
    with open(im_path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("investment", "").upper() == investment.upper():
                return dict(row)
    return {}


def _write_audit(portfolio_id: str, action: str, original_tranid: int,
                 new_tranid, actor: str, reason: str) -> None:
    audit_path = Path(FUNDS_PATH) / portfolio_id / "Events" / f"{portfolio_id}_audit.csv"
    fieldnames = ["timestamp", "action", "original_tranid", "new_tranid", "actor", "reason"]
    write_hdr  = not audit_path.exists() or os.path.getsize(audit_path) == 0
    row = {
        "timestamp":       datetime.now().strftime("%m/%d/%Y:%H:%M:%S"),
        "action":          action,
        "original_tranid": original_tranid,
        "new_tranid":      new_tranid or "",
        "actor":           actor or "ops",
        "reason":          reason or "",
    }
    with open(audit_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_hdr:
            writer.writeheader()
        writer.writerow(row)
    print(f">>> AUDIT | {portfolio_id} | {action} | original={original_tranid} new={new_tranid}")


def _clear_event_cache(portfolio_id: str) -> None:
    try:
        from process_portfolio import clear_event_cache
        clear_event_cache(portfolio_id)
        print(f">>> EVENT CACHE CLEARED via ops_routes | {portfolio_id}")
    except Exception as e:
        print(f">>> EVENT CACHE CLEAR FAILED | {portfolio_id} | {e}")


def _next_tranid(portfolio_dir: Path) -> int:
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
        dt = datetime.strptime(csv_date.split(":")[0], "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        try:
            datetime.strptime(csv_date[:10], "%Y-%m-%d")
            return csv_date[:10]
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")


def _method_to_transaction(method: str) -> str:
    mapping = {
        "buy_equity":        "EquityPurchase",
        "sell_equity":       "EquitySale",
        "short_equity":      "EquityShort",
        "cover_equity":      "EquityCover",
        "buy_bond":          "BondPurchase",
        "sell_bond":         "BondSale",
        "buy_future":        "FuturePurchase",
        "sell_future":       "FutureSale",
        "short_future":      "FutureShort",
        "cover_future":      "FutureCover",
        "buy_option":        "OptionPurchase",
        "sell_option":       "OptionSale",
        "short_option":      "OptionShort",
        "cover_option":      "OptionCover",
        "deposit_currency":  "CurrencyDeposit",
        "withdraw_currency": "CurrencyWithdrawal",
        "spot_fx":           "SpotFX",
        "dividend_equity":   "DividendEquity",
        "bond_coupon":       "BondCoupon",
        "split_equity":      "StockSplit",
        "mark_prices":       "PriceMark",
        "expense":           "Expense",
        "allocate":          "Allocation",
    }
    return mapping.get(method, method)