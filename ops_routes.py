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
from datetime import datetime

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


# ============================================================
# TEMPORAL METHOD HELPER
# ============================================================

def get_method_as_of(history: list, as_of_date: str) -> Optional[str]:
    """
    Get the effective method value as of a given date.
    Returns the most recent entry on or before as_of_date.
    History entries have keys: value, effective_from (YYYY-MM-DD).
    """
    if not history:
        return None
    applicable = [
        h for h in history
        if h.get("effective_from", "") <= as_of_date
    ]
    if not applicable:
        return history[0]["value"]  # fallback to first entry
    return applicable[-1]["value"]


def get_portfolio_config(portfolio_id: str) -> dict:
    """Load portfolio config. Raises 404 if not found."""
    config_path = Path(FUNDS_PATH) / portfolio_id / "portfolio.json"
    if not config_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Portfolio '{portfolio_id}' not found"
        )
    with open(config_path) as f:
        return json.load(f)


def save_portfolio_config(portfolio_id: str, config: dict) -> None:
    """Save portfolio config."""
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

    Directory structure created:
      funds/{portfolio_id}/
        portfolio.json        ← configuration with temporal method histories
        Candidates/           ← derived candidate list
        Events/               ← event CSV files
        RefData/              ← portfolio-specific IM and bond info
        Calendars/            ← snapshot and journal storage

    Non-temporal (set once, never changed):
      base_currency, domicile_country, inception_date

    Temporal (history maintained, effective by date):
      closing_method, accrual_method, amort_method
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

        # ── BUILD CONFIG WITH TEMPORAL METHOD HISTORIES ───────────
        config_data = {
            # Non-temporal — foundational, never changed
            "portfolio_id":     portfolio_id,
            "base_currency":    config.base_currency,
            "domicile_country": config.domicile_country,
            "inception_date":   config.inception_date,
            "managers":         config.managers,
            "description":      config.description,
            "status":           "active",
            "created_at":       datetime.now().isoformat(),

            # Calendars selected at creation
            "calendars":        calendars,

            # Temporal — history maintained, effective by date
            # Each history entry: {value, effective_from (YYYY-MM-DD)}
            "closing_method_history": [
                {
                    "value":          config.closing_method,
                    "effective_from": config.inception_date,
                }
            ],
            "accrual_method_history": [
                {
                    "value":          config.accrual_method,
                    "effective_from": config.inception_date,
                }
            ],
            "amort_method_history": [
                {
                    "value":          config.amort_method,
                    "effective_from": config.inception_date,
                }
            ],
        }

        # ── SAVE PORTFOLIO CONFIG ─────────────────────────────────
        config_path = portfolio_dir / "portfolio.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)

        # ── RESOLVE CALENDARS FROM PRESET OR EXPLICIT LIST ──────
        calendars = config.calendars
        if config.calendar_preset and config.calendar_preset in CALENDAR_PRESETS:
            calendars = CALENDAR_PRESETS[config.calendar_preset]

        if not calendars:
            calendars = ["Monthly"]

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
            "per_100FV_accrual", "per_100FV_amort",
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
    """
    ## Get Portfolio Configuration

    Returns the complete portfolio configuration including
    all temporal method histories.

    Also returns the current effective values as of today
    for convenience.
    """
    try:
        config = get_portfolio_config(portfolio_id)
        today  = datetime.now().strftime("%Y-%m-%d")

        # Add current effective values for convenience
        config["current"] = {
            "closing_method": get_method_as_of(
                config.get("closing_method_history", []), today),
            "accrual_method": get_method_as_of(
                config.get("accrual_method_history", []), today),
            "amort_method":   get_method_as_of(
                config.get("amort_method_history", []), today),
        }

        return config

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.get("/portfolios")
def list_portfolios():
    """List all portfolios with current effective method values."""
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
                "portfolio_id":   config.get("portfolio_id"),
                "description":    config.get("description"),
                "base_currency":  config.get("base_currency"),
                "domicile_country": config.get("domicile_country"),
                "inception_date": config.get("inception_date"),
                "managers":       config.get("managers", []),
                "status":         config.get("status"),
                "created_at":     config.get("created_at"),
                "closing_method": get_method_as_of(
                    config.get("closing_method_history", []), today),
                "accrual_method": get_method_as_of(
                    config.get("accrual_method_history", []), today),
                "amort_method":   get_method_as_of(
                    config.get("amort_method_history", []), today),
            })

        return {"portfolios": portfolios, "count": len(portfolios)}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.post("/portfolio/{portfolio_id}/method")
def update_method(
    portfolio_id:   str,
    method_type:    str = Query(...,
        description="closing_method | accrual_method | amort_method"),
    value:          str = Query(...,
        description="New value e.g. LIFO · accrue_bod · effective_yield"),
    effective_from: str = Query(...,
        description="Effective date YYYY-MM-DD"),
):
    """
    ## Update Portfolio Method (Going Forward)

    Appends a new entry to the method history.
    Does not affect past events — those already have the method stamped.
    No restatement. No accounting impact.

    Valid method_type values:
      closing_method  → FIFO · LIFO · AVGCOST
      accrual_method  → accrue_eod · accrue_bod · accrue_through_nonbusiness · accrue_skip_nonbusiness
      amort_method    → straight_line · effective_yield · constant_yield
    """
    try:
        valid_types = {"closing_method", "accrual_method", "amort_method"}
        if method_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"method_type must be one of: {sorted(valid_types)}"
            )

        config      = get_portfolio_config(portfolio_id)
        history_key = f"{method_type}_history"

        if history_key not in config:
            config[history_key] = []

        # Check not going back before inception
        if effective_from < config.get("inception_date", ""):
            raise HTTPException(
                status_code=400,
                detail=f"effective_from cannot be before inception_date "
                       f"({config.get('inception_date')})"
            )

        config[history_key].append({
            "value":          value,
            "effective_from": effective_from,
        })

        # Keep sorted chronologically
        config[history_key].sort(key=lambda h: h["effective_from"])

        save_portfolio_config(portfolio_id, config)

        print(f">>> METHOD UPDATED | {portfolio_id} | "
              f"{method_type}={value} from {effective_from}")

        return {
            "status":         "updated",
            "portfolio_id":   portfolio_id,
            "method_type":    method_type,
            "value":          value,
            "effective_from": effective_from,
            "history":        config[history_key],
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
    """
    ## Add Investment

    Adds an investment to the portfolio's investment master.
    Also appends to the global investment master if not present.

    Investment type drives accounting rules:
      EQUITY   — lot-level, FIFO/LIFO disposition
      BOND     — lot-level, accrual, amortization
      FUTURE   — contract-level, daily mark
      OPTION   — lot-level, premium accounting
      CURRENCY — average cost, no lots, is_currency=true
    """
    try:
        portfolio_dir = Path(FUNDS_PATH) / portfolio_id

        if not portfolio_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Portfolio '{portfolio_id}' not found"
            )

        im_path = portfolio_dir / "RefData" / "investment_master.csv"

        # Read existing
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
                detail=f"Investment '{investment.investment}' already exists "
                       f"in {portfolio_id}"
            )

        # Build record
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

        cols       = list(record.keys())
        write_hdr  = not im_path.exists() or os.path.getsize(im_path) == 0

        with open(im_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            if write_hdr:
                writer.writeheader()
            writer.writerow(record)

        # Also append to global IM if not present
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
            "status":       "added",
            "portfolio_id": portfolio_id,
            "investment":   investment.investment,
            "record":       record,
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@ops_router.get("/portfolio/{portfolio_id}/investments")
def list_investments(portfolio_id: str):
    """List all investments in the portfolio investment master."""
    try:
        im_path = (
            Path(FUNDS_PATH) / portfolio_id / "RefData" / "investment_master.csv"
        )
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
    ## Add Event

    Appends a single event to the portfolio's event file.
    closing_method is stamped on each event from the portfolio
    config as of the event's trade date — temporal method
    history ensures the correct method is always used.

    Events are not processed until /api/v1/cph/process is called.
    This allows Ops to enter, review, and validate before processing.

    Mark events (mark_prices) go to the _marks.csv file.
    All other events go to the main events CSV file.
    """
    try:
        portfolio_dir = Path(FUNDS_PATH) / portfolio_id

        if not portfolio_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Portfolio '{portfolio_id}' not found"
            )

        # Load config to get closing method as of trade date
        config       = get_portfolio_config(portfolio_id)
        trade_date   = _csv_date_to_ymd(event.tradedate)
        closing_meth = get_method_as_of(
            config.get("closing_method_history", []),
            trade_date
        ) or "FIFO"

        is_mark     = event.method == "mark_prices"
        events_file = portfolio_dir / "Events" / (
            f"{portfolio_id}_marks.csv" if is_mark
            else f"{portfolio_id}.csv"
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
            # Closing method stamped at event construction time
            "closing_method":    closing_meth,
        }

        fieldnames = list(row.keys())
        write_hdr  = not events_file.exists() or os.path.getsize(events_file) == 0

        with open(events_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_hdr:
                writer.writeheader()
            writer.writerow(row)

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
    limit:        int           = Query(100, ge=1, le=10000),
):
    """List events for a portfolio with optional filters."""
    try:
        events_file = (
            Path(FUNDS_PATH) / portfolio_id / "Events" / f"{portfolio_id}.csv"
        )
        if not events_file.exists():
            return {"events": [], "count": 0}

        events = []
        with open(events_file, newline="") as f:
            for row in csv.DictReader(f):
                if investment and row.get("investment") != investment:
                    continue
                if method and row.get("method") != method:
                    continue
                events.append(dict(row))
                if len(events) >= limit:
                    break

        return {"events": events, "count": len(events)}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# HELPERS
# ============================================================

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
    """
    Convert MM/DD/YYYY:HH:MM:SS to YYYY-MM-DD for method history lookup.
    Falls back gracefully if format is unexpected.
    """
    try:
        dt = datetime.strptime(csv_date.split(":")[0] +
                               ":" + csv_date.split(":")[1] +
                               ":" + csv_date.split(":")[2],
                               "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        try:
            # Try direct YYYY-MM-DD
            datetime.strptime(csv_date[:10], "%Y-%m-%d")
            return csv_date[:10]
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")


def _method_to_transaction(method: str) -> str:
    """Derive transaction label from method name."""
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