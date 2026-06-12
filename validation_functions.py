"""
validation_functions.py
Visibility Platform — Validation Function Library

Named functions referenced by validation_registry.json.
The registry declares WHAT and WHEN. This file defines HOW.

Every function here has a JavaScript mirror in validation_functions.js.
Do not add business logic anywhere else — if a computation or default
belongs to the platform, it lives here and is referenced by name in
the registry.

Function categories:
  default_fn   — populate a field from a known source (IM, portfolio config, date rule)
  compute_fn   — derive a field value from other field values
  validate_fn  — return True/False + message for a field or cross-field rule
  guard_fn     — pre-write checks that query state (positions, existence)
"""

from datetime import date, timedelta
from typing   import Any, Optional
import math


# ============================================================
# RESULT TYPES
# ============================================================

class DefaultResult:
    def __init__(self, value: Any, source: str, display_only: bool = False):
        self.value        = value
        self.source       = source
        self.display_only = display_only

class ComputeResult:
    def __init__(self, value: Any, formula: str, inputs: dict):
        self.value   = value
        self.formula = formula
        self.inputs  = inputs

class ValidationResult:
    def __init__(self, valid: bool, message: str = "", severity: str = "error"):
        self.valid    = valid
        self.message  = message
        self.severity = severity  # "error" | "warning"

class GuardResult:
    def __init__(self, passed: bool, message: str = ""):
        self.passed  = passed
        self.message = message


# ============================================================
# DEFAULT FUNCTIONS  (default_fn)
# Called on_investment_lookup — populate fields from IM or config
# ============================================================

def im_field(im_record: dict, field: str) -> DefaultResult:
    """
    Pull any field directly from the IM record.
    Used for: payment_currency, pricing_factor, country_of_risk,
              contract_size, underlying, put_call, strike.

    registry usage:
        "default_fn": "im_field"
        "args": {"field": "currency"}
    """
    value = im_record.get(field)
    return DefaultResult(
        value  = value,
        source = f"im.{field}"
    )


def portfolio_base_currency(portfolio_config: dict) -> DefaultResult:
    """
    Return the portfolio base currency.
    Used to determine whether FX conversion is needed
    (payment_currency == base_currency → no conversion).
    """
    return DefaultResult(
        value  = portfolio_config.get("base_currency", "USD"),
        source = "portfolio.base_currency"
    )


def settle_date_from_trade(trade_date: str, method: str,
                            calendar: str = "US_FEDERAL_HOLIDAYS") -> DefaultResult:
    """
    Auto-populate settle date from trade date using settle_rules in registry.

    T+2 methods: buy_equity, sell_equity, short_equity, cover_equity
    T+0 methods: everything else

    registry usage:
        "default_fn": "settle_date_from_trade"
        "when": "on_exit:tradedate"
    """
    T2_METHODS = {"buy_equity", "sell_equity", "short_equity", "cover_equity"}
    n = 2 if method in T2_METHODS else 0
    result = _add_business_days(trade_date, n, calendar)
    return DefaultResult(
        value  = result,
        source = f"settle_rule:T+{n}"
    )


def kdbegin_from_trade(trade_date: str) -> DefaultResult:
    """
    KD begin defaults to trade date.
    """
    return DefaultResult(
        value  = trade_date,
        source = "trade_date"
    )


# ============================================================
# COMPUTE FUNCTIONS  (compute_fn)
# Called on_exit — derive field values from user-entered inputs
# ============================================================

def qty_price_pf(quantity: float, price: float,
                  pricing_factor: float, fees: float = 0.0) -> ComputeResult:
    """
    Core trade amount computation.
    local_amount = quantity * price * pricing_factor + fees

    fees defaults to 0 — dormant until fees/commissions sprint.
    Applies to: EQUITY, OPTION (buy/sell/short/cover)

    registry usage:
        "compute_fn": "qty_price_pf"
        "on_exit": ["quantity", "price"]
    """
    value = quantity * price * pricing_factor + fees
    return ComputeResult(
        value   = round(value, 2),
        formula = "quantity * price * pricing_factor + fees",
        inputs  = {
            "quantity":       quantity,
            "price":          price,
            "pricing_factor": pricing_factor,
            "fees":           fees
        }
    )


def future_notional(quantity: float, price: float,
                     contract_size: float, pricing_factor: float) -> ComputeResult:
    """
    Futures notional — not a cash outlay, informational for risk/reporting.
    notional = quantity * price * contract_size * pricing_factor

    Also used for total_amount and total_amount_base on futures
    (futures have no cash settlement at open — notional IS the amount).

    registry usage:
        "compute_fn": "future_notional"
        "on_exit": ["quantity", "price"]
    """
    value = quantity * price * contract_size * pricing_factor
    return ComputeResult(
        value   = round(value, 2),
        formula = "quantity * price * contract_size * pricing_factor",
        inputs  = {
            "quantity":       quantity,
            "price":          price,
            "contract_size":  contract_size,
            "pricing_factor": pricing_factor
        }
    )


def future_unrealized(mark_price: float, trade_price: float, quantity: float,
                       contract_size: float, pricing_factor: float,
                       direction: str = "long") -> ComputeResult:
    """
    Futures unrealized P&L — price change only, NOT full notional.

    long:  unrealized = (mark_price - trade_price) * qty * contract_size * pf
    short: unrealized = (trade_price - mark_price) * qty * contract_size * pf

    This is the fix for the day-one marking issue — notional should never
    be used as the unrealized value.

    registry usage:
        "compute_fn": "future_unrealized"
        referenced in investment_types.FUTURE.unrealized_calc
    """
    delta = (mark_price - trade_price) if direction == "long" \
            else (trade_price - mark_price)
    value = delta * quantity * contract_size * pricing_factor
    return ComputeResult(
        value   = round(value, 2),
        formula = f"({mark_price} - {trade_price}) * {quantity} * {contract_size} * {pricing_factor}",
        inputs  = {
            "mark_price":     mark_price,
            "trade_price":    trade_price,
            "quantity":       quantity,
            "contract_size":  contract_size,
            "pricing_factor": pricing_factor,
            "direction":      direction
        }
    )


def bond_total_amount(quantity: float, price: float,
                       pricing_factor: float, accrued: float = 0.0) -> ComputeResult:
    """
    Bond total amount = notional * price + accrued interest
    notional = quantity * pricing_factor  (pricing_factor=0.01 for bonds)

    registry usage:
        "compute_fn": "bond_total_amount"
        "on_exit": ["quantity", "price", "accrued_local"]
    """
    notional = quantity * pricing_factor
    value    = notional * price + accrued
    return ComputeResult(
        value   = round(value, 2),
        formula = "quantity * pricing_factor * price + accrued",
        inputs  = {
            "quantity":       quantity,
            "price":          price,
            "pricing_factor": pricing_factor,
            "notional":       round(notional, 2),
            "accrued":        accrued
        }
    )


def local_times_fx(local_amount: float, fx_rate: float) -> ComputeResult:
    """
    Convert local amount to base currency (book amount).
    book_amount = local_amount * fx_rate

    fx_rate is resolved externally via fx_policy before this is called.
    If payment_currency == base_currency, engine sets fx_rate=1 and
    skips the API call — this function still runs cleanly.

    registry usage:
        "compute_fn": "local_times_fx"
        "on_exit": ["total_amount", "payment_currency"]
    """
    value = local_amount * fx_rate
    return ComputeResult(
        value   = round(value, 2),
        formula = "local_amount * fx_rate",
        inputs  = {
            "local_amount": local_amount,
            "fx_rate":      fx_rate
        }
    )


def dividend_total(per_share: float, current_position: float) -> ComputeResult:
    """
    Dividend / bond coupon total amount.
    total = per_share * current_long_position_quantity

    registry usage:
        "compute_fn": "dividend_total"
        "on_exit": ["per_share"]
    """
    value = per_share * current_position
    return ComputeResult(
        value   = round(value, 2),
        formula = "per_share * current_position",
        inputs  = {
            "per_share":         per_share,
            "current_position":  current_position
        }
    )


# ============================================================
# VALIDATE FUNCTIONS  (validate_fn)
# Return ValidationResult — used for field-level and cross-field rules
# ============================================================

def validate_required(value: Any, field: str) -> ValidationResult:
    """Generic required field check."""
    if value is None or value == "" or value == 0:
        return ValidationResult(False, f"{field} is required")
    return ValidationResult(True)


def validate_gt_zero(value: float, field: str) -> ValidationResult:
    """Value must be greater than zero."""
    if not isinstance(value, (int, float)) or value <= 0:
        return ValidationResult(False, f"{field} must be greater than zero")
    return ValidationResult(True)


def validate_enum(value: str, allowed: list, field: str) -> ValidationResult:
    """Value must be one of a defined set."""
    if value not in allowed:
        return ValidationResult(
            False,
            f"{field} must be one of: {', '.join(allowed)} — got '{value}'"
        )
    return ValidationResult(True)


def validate_iso_currency(value: str) -> ValidationResult:
    """ISO 4217 three-letter currency code."""
    import re
    if not re.match(r'^[A-Z]{3}$', value or ''):
        return ValidationResult(
            False,
            f"Currency must be a 3-letter ISO code (e.g. USD, EUR, GBP) — got '{value}'"
        )
    return ValidationResult(True)


def validate_iso_country(value: str) -> ValidationResult:
    """ISO 3166-1 alpha-2 two-letter country code."""
    import re
    if not re.match(r'^[A-Z]{2}$', value or ''):
        return ValidationResult(
            False,
            f"Country must be a 2-letter ISO code (e.g. US, JP, GB) — got '{value}'"
        )
    return ValidationResult(True)


def validate_settle_gte_trade(trade_date: str, settle_date: str) -> ValidationResult:
    """Settle date must be on or after trade date."""
    try:
        td = date.fromisoformat(trade_date)
        sd = date.fromisoformat(settle_date)
        if sd < td:
            return ValidationResult(
                False,
                f"Settle date ({settle_date}) cannot be before trade date ({trade_date})"
            )
        return ValidationResult(True)
    except ValueError as e:
        return ValidationResult(False, f"Invalid date format: {e}")


def validate_investment_type_matches_method(
        actual_type: str, required_type: str,
        investment: str, method: str) -> ValidationResult:
    """Investment type in IM must match what the method requires."""
    if actual_type.upper() != required_type.upper():
        return ValidationResult(
            False,
            f"Type mismatch — {investment} is {actual_type} "
            f"but {method} requires {required_type}"
        )
    return ValidationResult(True)


def validate_bond_price_range(price: float) -> ValidationResult:
    """
    Bond price sanity check — prices are per 100 face value.
    A price > 200 almost certainly means the user entered notional
    instead of the clean price.
    """
    if price > 200:
        return ValidationResult(
            False,
            f"Bond price {price} seems too high — price should be per 100 face value "
            f"(e.g. 98.5, not 985000). Did you enter the notional amount?",
            severity="warning"
        )
    return ValidationResult(True)


def validate_effective_from_not_before_inception(
        effective_from: str, inception_date: str) -> ValidationResult:
    """Method update effective_from cannot predate portfolio inception."""
    try:
        ef = date.fromisoformat(effective_from)
        inc = date.fromisoformat(inception_date)
        if ef < inc:
            return ValidationResult(
                False,
                f"effective_from ({effective_from}) cannot be before "
                f"portfolio inception ({inception_date})"
            )
        return ValidationResult(True)
    except ValueError as e:
        return ValidationResult(False, f"Invalid date format: {e}")


def validate_portfolio_id_format(portfolio_id: str) -> ValidationResult:
    """Portfolio ID — no spaces or special characters."""
    import re
    if not re.match(r'^[A-Za-z0-9_]+$', portfolio_id or ''):
        return ValidationResult(
            False,
            f"Portfolio ID must contain only letters, numbers, and underscores — "
            f"no spaces or special characters"
        )
    return ValidationResult(True)


def validate_spot_fx_currencies_differ(
        buy_currency: str, sell_currency: str) -> ValidationResult:
    """Buy and sell currency cannot be the same on a spot FX trade."""
    if buy_currency and sell_currency and buy_currency == sell_currency:
        return ValidationResult(
            False,
            f"Buy and sell currency cannot both be {buy_currency}"
        )
    return ValidationResult(True)


# ============================================================
# GUARD FUNCTIONS  (guard_fn)
# Pre-write state checks — query positions, existence, duplicates
# ============================================================

def guard_event_exists(portfolio_dir, tranid: int) -> GuardResult:
    """Event must exist before it can be reversed or modified."""
    import csv
    from pathlib import Path
    events_file = Path(portfolio_dir) / "Events" / f"{Path(portfolio_dir).name}.csv"
    if not events_file.exists():
        return GuardResult(False, f"Events file not found for portfolio")
    with open(events_file, newline="") as f:
        for row in csv.DictReader(f):
            if int(row.get("tranid", 0)) == tranid:
                return GuardResult(True)
    return GuardResult(False, f"Event tranid={tranid} not found")


def guard_event_not_reversed(portfolio_dir, tranid: int) -> GuardResult:
    """Event must not already be reversed (kdend != 12/31/2099)."""
    import csv
    from pathlib import Path
    events_file = Path(portfolio_dir) / "Events" / f"{Path(portfolio_dir).name}.csv"
    with open(events_file, newline="") as f:
        for row in csv.DictReader(f):
            if int(row.get("tranid", 0)) == tranid:
                if row.get("kdend", "12/31/2099:00:00:00") != "12/31/2099:00:00:00":
                    return GuardResult(
                        False,
                        f"Event tranid={tranid} is already reversed"
                    )
                return GuardResult(True)
    return GuardResult(False, f"Event tranid={tranid} not found")


def guard_investment_exists_in_im(im_map: dict, investment: str,
                                   portfolio: str) -> GuardResult:
    """Investment must exist in portfolio IM before event entry."""
    if investment.upper() not in {k.upper() for k in im_map}:
        return GuardResult(
            False,
            f"{investment} not found in {portfolio} IM"
        )
    return GuardResult(True)


def guard_contract_size_nonzero(im_record: dict, investment: str) -> GuardResult:
    """contract_size must be non-zero in IM before any future event."""
    cs = float(im_record.get("contract_size", 0) or 0)
    if cs == 0:
        return GuardResult(
            False,
            f"contract_size is 0 for {investment} — update IM before entering future events"
        )
    return GuardResult(True)


def guard_bond_info_exists(portfolio_dir, investment: str) -> GuardResult:
    """bond_info refdata must exist before any bond event."""
    import csv
    from pathlib import Path
    bond_info_path = Path(portfolio_dir) / "RefData" / "bond_info.csv"
    if not bond_info_path.exists():
        return GuardResult(False, f"bond_info.csv not found in {Path(portfolio_dir).name} RefData")
    with open(bond_info_path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("investment", "").upper() == investment.upper():
                return GuardResult(True)
    return GuardResult(
        False,
        f"bond_info not found for {investment} — add before entering bond events"
    )


# ============================================================
# PRIVATE HELPERS
# ============================================================

US_HOLIDAYS = {
    "2024-01-01","2024-01-15","2024-02-19","2024-05-27","2024-06-19",
    "2024-07-04","2024-09-02","2024-10-14","2024-11-11","2024-11-28","2024-12-25",
    "2025-01-01","2025-01-20","2025-02-17","2025-05-26","2025-06-19",
    "2025-07-04","2025-09-01","2025-10-13","2025-11-11","2025-11-27","2025-12-25",
    "2026-01-01","2026-01-19","2026-02-16","2026-05-25","2026-06-19",
    "2026-07-03","2026-09-07","2026-10-12","2026-11-11","2026-11-26","2026-12-25",
    "2027-01-01","2027-01-18","2027-02-15","2027-05-31","2027-07-05",
    "2027-09-06","2027-10-11","2027-11-11","2027-11-25","2027-12-24",
}

def _is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in US_HOLIDAYS

def _add_business_days(date_str: str, n: int, calendar: str = "US_FEDERAL_HOLIDAYS") -> str:
    d = date.fromisoformat(date_str)
    added = 0
    while added < n:
        d += timedelta(days=1)
        if _is_business_day(d):
            added += 1
    return d.isoformat()


# ============================================================
# FUNCTION REGISTRY
# Maps string names (used in validation_registry.json) to functions.
# Engine resolves names at runtime via this dict.
# ============================================================

DEFAULT_FUNCTIONS = {
    "im_field":               im_field,
    "portfolio_base_currency":portfolio_base_currency,
    "settle_date_from_trade": settle_date_from_trade,
    "kdbegin_from_trade":     kdbegin_from_trade,
}

COMPUTE_FUNCTIONS = {
    "qty_price_pf":           qty_price_pf,
    "future_notional":        future_notional,
    "future_unrealized":      future_unrealized,
    "bond_total_amount":      bond_total_amount,
    "local_times_fx":         local_times_fx,
    "dividend_total":         dividend_total,
}

VALIDATE_FUNCTIONS = {
    "required":                         validate_required,
    "gt_zero":                          validate_gt_zero,
    "enum":                             validate_enum,
    "iso_currency":                     validate_iso_currency,
    "iso_country":                      validate_iso_country,
    "settle_gte_trade":                 validate_settle_gte_trade,
    "investment_type_matches_method":   validate_investment_type_matches_method,
    "bond_price_range":                 validate_bond_price_range,
    "effective_from_not_before_inception": validate_effective_from_not_before_inception,
    "portfolio_id_format":              validate_portfolio_id_format,
    "spot_fx_currencies_differ":        validate_spot_fx_currencies_differ,
}

GUARD_FUNCTIONS = {
    "event_exists":             guard_event_exists,
    "event_not_reversed":       guard_event_not_reversed,
    "investment_exists_in_im":  guard_investment_exists_in_im,
    "contract_size_nonzero":    guard_contract_size_nonzero,
    "bond_info_exists":         guard_bond_info_exists,
}


def validate_market_tolerance(
        user_value:    float,
        file_value:    float,
        field:         str,
        tolerance_pct: float,
        line:          int = 1) -> ValidationResult:
    """
    Market reasonableness check.
    Fires at all three defense lines — severity response differs by caller.

    Line 1 (entry)      → warning, user can acknowledge and proceed
    Line 2 (processing) → logged in processing report, optionally halt
    Line 3 (proof)      → flagged in proof report, requires sign-off

    registry usage:
        "validate_fn": "market_tolerance"
        "args": {"field": "price"}  -- engine resolves tolerance_pct from
                                       platform.tolerance_bands[field]
    """
    if file_value is None or file_value == 0:
        # No reference value available — cannot check, pass with info
        return ValidationResult(
            valid    = True,
            message  = f"No file {field} available for tolerance check — skipped",
            severity = "info"
        )

    deviation_pct = abs(user_value - file_value) / abs(file_value) * 100

    if deviation_pct > tolerance_pct:
        return ValidationResult(
            valid    = False,
            message  = (
                f"{field} {user_value:,.4f} deviates {deviation_pct:.1f}% "
                f"from file value {file_value:,.4f} "
                f"— exceeds {tolerance_pct}% band"
            ),
            severity = "warning"
        )

    return ValidationResult(True)


# Register it
VALIDATE_FUNCTIONS["market_tolerance"] = validate_market_tolerance


def csv_date_to_iso(csv_date: str) -> str:
    """
    Convert CPH event date format (MM/DD/YYYY:HH:MM:SS) to ISO (YYYY-MM-DD).
    Needed because validation_engine expects ISO dates.
    """
    try:
        return f"{csv_date[6:10]}-{csv_date[0:2]}-{csv_date[3:5]}"
    except Exception:
        return csv_date


def event_row_to_payload(event: dict) -> dict:
    """
    Convert a raw CPH event dict (CSV field names, CSV date format)
    to a validation payload (ISO dates, numeric types).
    Called by Line 2 before validate_event().
    """
    def _num(v, default=0.0):
        try:
            return float(v) if v not in (None, "", "0", 0) else default
        except (ValueError, TypeError):
            return default

    return {
        "portfolio":          event.get("portfolio", ""),
        "method":             event.get("method", ""),
        "investment":         event.get("investment", ""),
        "payment_currency":   event.get("payment_currency", ""),
        "tradedate":          csv_date_to_iso(event.get("tradedate", "")),
        "settledate":         csv_date_to_iso(event.get("settledate", "")),
        "quantity":           _num(event.get("quantity")),
        "price":              _num(event.get("price")),
        "notional":           _num(event.get("notional")),
        "total_amount":       _num(event.get("total_amount")),
        "total_amount_base":  _num(event.get("total_amount_base")),
        "accrued_local":      _num(event.get("accrued_local")),
        "accrued_book":       _num(event.get("accrued_book")),
        "per_share":          _num(event.get("per_share")),
        "new_shares":         _num(event.get("new_shares")),
        "old_shares":         _num(event.get("old_shares")),
        "buy_currency":       event.get("buy_currency") or None,
        "sell_currency":      event.get("sell_currency") or None,
        "buy_amt":            _num(event.get("buy_amt")),
        "sell_amt":           _num(event.get("sell_amt")),
        "tranid":             event.get("tranid", ""),
        "closing_method":     event.get("closing_method", ""),
        "location":           event.get("location", ""),
        "strategy":           event.get("strategy", ""),
    }


VALIDATE_FUNCTIONS["csv_date_to_iso"]    = csv_date_to_iso
VALIDATE_FUNCTIONS["event_row_to_payload"] = event_row_to_payload


def get_file_fx_rate(
        payment_currency: str,
        base_currency:    str,
        trade_date:       str,
        refdata_path:     str = None) -> float:
    """
    Look up FX rate from fx_master.csv.

    Schema: date | currency | price
    Rates are quoted in USD terms — price IS the USD equivalent rate.

    Same currency → 1.0
    Otherwise     → look up payment_currency row for trade_date, return price directly.
    No cross-rate math needed — file is always USD-based.

    Dates are normalized to YYYY-MM-DD on BOTH sides before comparing, because
    the file stores M/D/YYYY (e.g. "1/5/2026") while callers pass ISO
    ("2026-01-05"). A raw string compare misses every time otherwise.
    """
    import csv
    import os

    if payment_currency == base_currency:
        return 1.0

    if payment_currency == "USD":
        return 1.0

    if refdata_path is None:
        refdata_path = os.environ.get("VISIBILITY_REFDATA_PATH", "refdata")

    fx_path = os.path.join(refdata_path, "fx_master.csv")
    if not os.path.exists(fx_path):
        return None

    def _norm_date(val: str) -> str:
        """Normalize '1/5/2026', '01/05/2026', '2026-01-05', or any of those
        with a ':00:00:00' / 'T00:00:00' time suffix → 'YYYY-MM-DD'."""
        if not val:
            return ""
        val = str(val).strip()
        if "/" in val:                       # M/D/YYYY (optionally with time suffix)
            parts = val.split("/")
            if len(parts) >= 3:
                m = parts[0].zfill(2)
                d = parts[1].zfill(2)
                y = parts[2].split(":")[0].split("T")[0].strip()
                return f"{y}-{m}-{d}"
        if len(val) >= 10 and val[4] == "-": # ISO (optionally with time suffix)
            return val[:10]
        return val

    trade_date_norm = _norm_date(trade_date)

    with open(fx_path, newline="") as f:
        for row in csv.DictReader(f):
            row_date = _norm_date(str(row.get("date", "")))
            ccy      = str(row.get("currency", "")).strip().upper()
            if row_date == trade_date_norm and ccy == payment_currency.upper():
                try:
                    return float(row.get("price", 0) or 0)
                except (ValueError, TypeError):
                    return None

    return None
DEFAULT_FUNCTIONS["get_file_fx_rate"] = get_file_fx_rate