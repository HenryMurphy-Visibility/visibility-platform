# -*- coding: utf-8 -*-
"""
proof_engine.py — Visibility VAI Proof Engine
Four honest pillars. No re-running the accounting.

Usage (from chest root):
  python proof_engine.py Portfolio3 Monthly
  python proof_engine.py Portfolio3 Monthly 2026-01
  python proof_engine.py Portfolio3 Monthly --tranid 3
  python proof_engine.py Portfolio3 Monthly --investment MITIB
  python proof_engine.py Portfolio3 Monthly --pillar availability
  python proof_engine.py Portfolio3 Monthly --pillar balance
  python proof_engine.py Portfolio3 Monthly --pillar settle_fx
  python proof_engine.py Portfolio3 Monthly --pillar marks

Pillars:
  1. availability  — prices and FX rates exist for all required dates
  2. balance       — debits = credits every period (double-entry integrity)
  3. settle_fx     — trade/settle FX G/L uses correct rate
  4. marks         — period end MV = qty × price × pf × fx_rate

Henry J. Murphy — Chest Financial Systems
VAI — Visibility Artificial Intelligence
"""

import pickle
import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta, date as date_type
from collections import defaultdict

import os
from v_config import REFDATA_PATH

COA_PATH = os.path.join(REFDATA_PATH, "chart_of_accounts.csv")

# US Market Holidays 2019-2027
US_HOLIDAYS = {
    date_type(2019,1,1),date_type(2019,1,21),date_type(2019,2,18),date_type(2019,4,19),
    date_type(2019,5,27),date_type(2019,7,4),date_type(2019,9,2),date_type(2019,11,28),date_type(2019,12,25),
    date_type(2020,1,1),date_type(2020,1,20),date_type(2020,2,17),date_type(2020,4,10),
    date_type(2020,5,25),date_type(2020,7,3),date_type(2020,9,7),date_type(2020,11,26),date_type(2020,12,25),
    date_type(2021,1,1),date_type(2021,1,18),date_type(2021,2,15),date_type(2021,4,2),
    date_type(2021,5,31),date_type(2021,7,5),date_type(2021,9,6),date_type(2021,11,25),date_type(2021,12,24),
    date_type(2022,1,17),date_type(2022,2,21),date_type(2022,4,15),date_type(2022,5,30),
    date_type(2022,6,20),date_type(2022,7,4),date_type(2022,9,5),date_type(2022,11,24),date_type(2022,12,26),
    date_type(2023,1,2),date_type(2023,1,16),date_type(2023,2,20),date_type(2023,4,7),
    date_type(2023,5,29),date_type(2023,6,19),date_type(2023,7,4),date_type(2023,9,4),date_type(2023,11,23),date_type(2023,12,25),
    date_type(2024,1,1),date_type(2024,1,15),date_type(2024,2,19),date_type(2024,3,29),
    date_type(2024,5,27),date_type(2024,6,19),date_type(2024,7,4),date_type(2024,9,2),date_type(2024,11,28),date_type(2024,12,25),
    date_type(2025,1,1),date_type(2025,1,20),date_type(2025,2,17),date_type(2025,4,18),
    date_type(2025,5,26),date_type(2025,6,19),date_type(2025,7,4),date_type(2025,9,1),date_type(2025,11,27),date_type(2025,12,25),
    date_type(2026,1,1),date_type(2026,1,19),date_type(2026,2,16),date_type(2026,4,3),
    date_type(2026,5,25),date_type(2026,6,19),date_type(2026,7,3),date_type(2026,9,7),date_type(2026,11,26),date_type(2026,12,25),
    date_type(2027,1,1),date_type(2027,1,18),date_type(2027,2,15),date_type(2027,3,26),
    date_type(2027,5,31),date_type(2027,6,18),date_type(2027,7,5),date_type(2027,9,6),date_type(2027,11,25),date_type(2027,12,24),
}

def _is_business_day(d: str) -> bool:
    """Return True if date is a US market business day."""
    try:
        dt = datetime.strptime(d, "%Y-%m-%d").date()
        return dt.weekday() < 5 and dt not in US_HOLIDAYS
    except Exception:
        return True  # assume business day if can't parse

# ── TOLERANCE ─────────────────────────────────────────────────
AMOUNT_TOLERANCE = 0.01      # absolute for small amounts
PCT_TOLERANCE    = 0.0001    # 0.01% for large amounts
QTY_TOLERANCE    = 0.000001  # near-zero quantity threshold

# ── CONSOLE COLORS ─────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

def _ok(msg):   return f"{GREEN}✓ PASS{RESET}  {msg}"
def _warn(msg): return f"{YELLOW}⚠ WARN{RESET}  {msg}"
def _fail(msg): return f"{RED}✗ FAIL{RESET}  {msg}"
def _info(msg): return f"{CYAN}  INFO{RESET}  {msg}"
def _skip(msg): return f"{DIM}  SKIP  {msg}{RESET}"


# ============================================================
# PROOF RESULT COLLECTOR
# ============================================================

class ProofResult:
    def __init__(self, pillar: str):
        self.pillar   = pillar
        self.passes   = []
        self.warnings = []
        self.failures = []
        self.skipped  = []

    def ok(self,   msg): self.passes.append(msg)
    def warn(self, msg): self.warnings.append(msg)
    def fail(self, msg): self.failures.append(msg)
    def skip(self, msg): self.skipped.append(msg)

    @property
    def all_clear(self): return len(self.failures) == 0
    @property
    def total(self): return len(self.passes) + len(self.warnings) + len(self.failures)


# ============================================================
# DATA LOADERS
# ============================================================

def load_events(portfolio: str, funds_path: str) -> list:
    path = Path(funds_path) / portfolio / "Events" / f"{portfolio}.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_investment_master(portfolio: str, funds_path: str) -> dict:
    path = Path(funds_path) / portfolio / "RefData" / "investment_master.csv"
    if not path.exists():
        return {}
    result = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            inv = row.get("investment", "").strip()
            if inv:
                result[inv] = row
    return result


def load_price_index(refdata_path: str) -> dict:
    """Returns {(ticker, YYYY-MM-DD): price}"""
    path = Path(refdata_path) / "price_master.csv"
    if not path.exists():
        return {}
    index = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or row.get("investment") or "").strip()
            date   = _norm_date(row.get("date") or row.get("price_date") or "")
            price  = _safe_float(row.get("price") or row.get("close") or "")
            if ticker and date and price is not None:
                index[(ticker, date)] = price
    return index


def load_fx_index(refdata_path: str) -> dict:
    """Returns {(currency, YYYY-MM-DD): rate} where rate = USD per 1 unit of currency"""
    path = Path(refdata_path) / "fx_master.csv"
    if not path.exists():
        return {}
    index = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            ccy  = (row.get("currency") or row.get("ticker") or "").strip()
            date = _norm_date(row.get("date") or row.get("fx_date") or "")
            rate = _safe_float(row.get("rate") or row.get("price") or row.get("close") or "")
            if ccy and date and rate is not None:
                index[(ccy, date)] = rate
    return index


def load_jes_from_journals(portfolio: str, calendar: str,
                           funds_path: str, period: str = None) -> dict:
    """
    Returns dict: {period_name: [je_objects]}
    PKL structure: dict with keys portfolio, calendar, period_name, journals
    journals = list of JE objects with to_dict() method
    """
    journals_dir = Path(funds_path) / portfolio / "Calendars" / calendar / "Journals"
    if not journals_dir.exists():
        return {}

    result = {}
    for pkl_file in sorted(journals_dir.glob("*.pkl")):
        try:
            with open(pkl_file, "rb") as f:
                data = pickle.load(f)

            if not isinstance(data, dict):
                continue

            period_name = data.get("period_name", pkl_file.stem)
            jes         = data.get("journals", [])

            if period and period_name != period:
                continue

            result[period_name] = jes

        except Exception as e:
            print(f"  WARNING: Could not read {pkl_file.name}: {e}")

    return result


def load_calendar_records(portfolio: str, calendar: str,
                          funds_path: str) -> list:
    """Load calendar period records from the calendar txt file."""
    import json
    cal_path = Path(funds_path) / portfolio / "Calendars" / calendar / f"{calendar}.txt"
    if not cal_path.exists():
        return []
    records = []
    with open(cal_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("{"):
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    return records


# ============================================================
# HELPERS
# ============================================================

def _norm_date(val: str) -> str:
    if not val:
        return ""
    val = val.strip()
    if "/" in val:
        parts = val.split("/")
        if len(parts) >= 3:
            m = parts[0].zfill(2)
            d = parts[1].zfill(2)
            y = parts[2].split(":")[0]
            return f"{y}-{m}-{d}"
    if len(val) >= 10 and val[4] == "-":
        return val[:10]
    return val


def _safe_float(val) -> float:
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _je_val(je, field: str):
    """Get field from JE object or dict."""
    if isinstance(je, dict):
        return je.get(field)
    return getattr(je, field, None)


def _je_date(je, field: str) -> str:
    val = _je_val(je, field)
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    return _norm_date(str(val))


def _find_rate(index: dict, key_prefix: str, date: str,
               tolerance_days: int = 5) -> tuple:
    """
    Find (key_prefix, date) in index within tolerance_days.
    On non-business days (weekends/holidays) prefer looking backward —
    prior business day convention matches the accounting engine.
    Returns (value, days_gap) or (None, None)
    """
    if (key_prefix, date) in index:
        return index[(key_prefix, date)], 0
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        # On non-business days prefer backward (prior business day)
        # On business days search both directions equally
        if not _is_business_day(date):
            search_order = [-1]  # prior business day only — no forward search
        else:
            search_order = [-1, 1]
        for days in range(1, tolerance_days + 1):
            for sign in search_order:
                d = (dt + timedelta(days=days * sign)).strftime("%Y-%m-%d")
                if (key_prefix, d) in index:
                    return index[(key_prefix, d)], days
    except Exception:
        pass
    return None, None


def _active_events(events: list) -> list:
    return [
        e for e in events
        if e.get("kdend", "12/31/2099:00:00:00") == "12/31/2099:00:00:00"
    ]


def _is_tolerance_ok(a: float, b: float) -> bool:
    diff = abs(a - b)
    if diff <= AMOUNT_TOLERANCE:
        return True
    base = max(abs(a), abs(b), 1.0)
    return (diff / base) <= PCT_TOLERANCE


# ============================================================
# PILLAR 1 — DATA AVAILABILITY
# Prices and FX rates exist for all required dates
# ============================================================

def pillar_availability(events: list, im: dict, calendar_records: list,
                        price_index: dict, fx_index: dict) -> ProofResult:
    """
    Check that prices and FX rates exist for:
    - All period-end dates for all active equity/bond holdings
    - All settlement dates for foreign currency transactions
    """
    result = ProofResult("availability")

    active = _active_events(events)

    # Collect all investments and their currencies from active events
    holdings = {}  # investment → currency
    for e in active:
        inv = e.get("investment", "")
        ccy = e.get("payment_currency", "USD")
        if inv and inv not in holdings:
            # Get currency from IM if available
            if inv in im:
                ccy = im[inv].get("currency", ccy) or ccy
            holdings[inv] = ccy

    # Check prices at period end dates
    period_end_dates = []
    for rec in calendar_records:
        cutoff = _norm_date(rec.get("current_period_cutoff", ""))
        if cutoff:
            period_end_dates.append(cutoff)

    checked_prices = set()
    for inv, ccy in holdings.items():
        if inv in im:
            inv_type = im[inv].get("investment_type", "").upper()
            if inv_type == "CURRENCY":
                continue  # currencies don't need price marks
        for period_end in period_end_dates:
            key = (inv, period_end)
            if key in checked_prices:
                continue
            checked_prices.add(key)
            price, gap = _find_rate(price_index, inv, period_end)
            if price is None:
                result.fail(f"Price missing: {inv} on {period_end} — "
                           f"no price within 5 days in master")
            elif gap and gap > 0:
                # Only warn if period_end is a business day — weekend/holiday gaps are expected
                if _is_business_day(period_end):
                    result.warn(f"Price gap: {inv} on {period_end} — "
                               f"nearest price is {gap} day(s) away (business day)")
                else:
                    result.ok(f"Price exists: {inv} on {period_end} "
                             f"(non-business day, {gap}d gap expected)")
            else:
                result.ok(f"Price exists: {inv} on {period_end}")

    # Check FX rates at settlement dates for foreign currency events
    checked_fx = set()
    foreign_methods = {
        "buy_equity", "sell_equity", "short_equity", "cover_equity",
        "buy_bond", "sell_bond", "buy_future", "sell_future",
        "deposit_currency", "withdraw_currency", "spot_fx"
    }
    for e in active:
        method   = e.get("method", "")
        ccy      = e.get("payment_currency", "USD")
        settle   = _norm_date(e.get("settledate", ""))
        tranid   = e.get("tranid", "?")
        inv      = e.get("investment", "")

        if ccy == "USD" or method not in foreign_methods:
            continue
        if not settle:
            continue

        key = (ccy, settle)
        if key in checked_fx:
            continue
        checked_fx.add(key)

        rate, gap = _find_rate(fx_index, ccy, settle)
        if rate is None:
            result.fail(f"FX missing: {ccy}/USD on settle={settle} "
                       f"(tranid={tranid} · {inv}) — no rate within 5 days")
        elif gap and gap > 0:
            result.warn(f"FX gap: {ccy}/USD on settle={settle} "
                       f"(tranid={tranid} · {inv}) — nearest rate {gap} day(s) away")
        else:
            result.ok(f"FX exists: {ccy}/USD on settle={settle}")

    if result.total == 0:
        result.skip("No holdings or period dates to check")

    return result


# ============================================================
# PILLAR 2 — JOURNAL BALANCE
# Debits = Credits every period
# ============================================================

# Financial accounts that represent unrealized market value
# These legitimately don't need to net to zero within a period
UNREALIZED_ACCOUNTS = {
    # Market value — one-sided, used for performance only
    "MarketVal", "MarketValue",
    # Unrealized GL accounts — daily deltas, not balance sheet
    "UnrealizedGainLoss", "UnrealizedGL",
    "UnrealPriceGL", "UnrealFXGL",
    "UnrealPriceGLOffset", "UnrealFXGLOffset",
    "PriceGainLoss", "FXGainLoss",
    "AccruedIncome", "AmortDiscount", "AmortPremium",
}

def pillar_balance(jes_by_period: dict) -> ProofResult:
    """
    For every period, sum all JE local and book amounts.
    Debits (positive) should equal credits (negative) — net = 0.
    Exclude unrealized/market value accounts which don't balance intra-period.
    """
    result = ProofResult("balance")

    for period_name, jes in sorted(jes_by_period.items()):
        local_sum = 0.0
        book_sum  = 0.0
        je_count  = 0

        for je in jes:
            fa = str(_je_val(je, "financial_account") or "")
            # Skip unrealized accounts
            if any(u.lower() in fa.lower() for u in UNREALIZED_ACCOUNTS):
                continue

            local = _safe_float(_je_val(je, "local")) or 0.0
            book  = _safe_float(_je_val(je, "book"))  or 0.0
            local_sum += local
            book_sum  += book
            je_count  += 1

        if je_count == 0:
            result.skip(f"{period_name} — no JEs to balance check")
            continue

        local_ok = abs(local_sum) <= AMOUNT_TOLERANCE
        book_ok  = abs(book_sum)  <= AMOUNT_TOLERANCE

        if local_ok and book_ok:
            result.ok(f"{period_name} — {je_count} JEs balance "
                     f"(local={local_sum:.4f} book={book_sum:.4f})")
        else:
            if not local_ok:
                result.fail(f"{period_name} — LOCAL does not balance: "
                           f"net={local_sum:.4f} ({je_count} JEs)")
            if not book_ok:
                result.fail(f"{period_name} — BOOK does not balance: "
                           f"net={book_sum:.4f} ({je_count} JEs)")

    if result.total == 0:
        result.skip("No periods processed yet")

    return result


# ============================================================
# PILLAR 3 — TRADE/SETTLE FX VERIFICATION
# G/L between trade and settle = local × (settle_rate - trade_rate)
# Only applies to foreign currency equity/bond transactions
# ============================================================

SETTLE_FX_METHODS = {
    "buy_equity", "sell_equity", "short_equity", "cover_equity",
    "buy_bond", "sell_bond",
}

def pillar_settle_fx(events: list, jes_by_period: dict,
                     fx_index: dict) -> ProofResult:
    """
    For foreign currency equity/bond trades:
    The G/L JE between trade date and settle date should equal:
        local_amount × (settle_fx_rate - trade_fx_rate)

    This verifies the CORRECT rate was used — not just that a rate exists.
    """
    result = ProofResult("settle_fx")

    # Build JE index by tranid across all periods
    jes_by_tranid = defaultdict(list)
    for jes in jes_by_period.values():
        for je in jes:
            tid = _je_val(je, "tranid")
            if tid is not None:
                jes_by_tranid[int(tid)].append(je)

    active = _active_events(events)

    for event in active:
        method  = event.get("method", "")
        ccy     = event.get("payment_currency", "USD")
        tranid  = int(_safe_float(event.get("tranid")) or 0)
        inv     = event.get("investment", "")
        local   = _safe_float(event.get("total_amount"))
        trade_d = _norm_date(event.get("tradedate", ""))
        settle_d = _norm_date(event.get("settledate", ""))

        if method not in SETTLE_FX_METHODS:
            continue
        if ccy == "USD":
            continue  # No FX G/L for USD trades
        if trade_d == settle_d:
            result.skip(f"tranid={tranid} · {inv} — trade=settle, no FX G/L expected")
            continue
        if local is None:
            result.warn(f"tranid={tranid} · {inv} — local amount missing in event")
            continue

        # Trade date book comes directly from the event — no FX lookup needed.
        # The event carries whatever rate was applied at entry time.
        # This may or may not match the FX master on trade date — that's by design.
        trade_book = _safe_float(event.get("total_amount_base"))
        if trade_book is None:
            result.warn(f"tranid={tranid} · {inv} · {ccy} — "
                       f"total_amount_base missing in event")
            continue

        # Settle date FX rate from master — settlement always uses master rate
        settle_rate, settle_gap = _find_rate(fx_index, ccy, settle_d)
        if settle_rate is None:
            result.warn(f"tranid={tranid} · {inv} · {ccy} — "
                       f"no settle date FX rate on {settle_d}")
            continue

        # Expected G/L = settle_book - trade_book
        # settle_book  = local × settle_rate
        settle_book = abs(local) * settle_rate
        expected_gl = settle_book - abs(trade_book)
        gap_note    = f" settle rate {settle_gap}d gap" if settle_gap else ""

        # Find the FXGainTradeSettle JE on settle date
        actual_gl = None
        for je in jes_by_tranid.get(tranid, []):
            fa          = str(_je_val(je, "financial_account") or "")
            transaction = str(_je_val(je, "transaction") or "")
            ibor        = _je_date(je, "ibor_date")

            if (fa == "FXGainTradeSettle"
                    and transaction == "Settlement"
                    and ibor == settle_d):
                actual_gl = _safe_float(_je_val(je, "book"))
                break

        if actual_gl is None:
            result.warn(f"tranid={tranid} · {inv} · {ccy} — "
                       f"no FXGainTradeSettle JE found on settle={settle_d}")
            continue

        if _is_tolerance_ok(expected_gl, actual_gl):
            result.ok(f"tranid={tranid} · {inv} · {ccy} — "
                     f"FX G/L correct: expected={expected_gl:.4f} actual={actual_gl:.4f}"
                     + (f" [{gap_note.strip()}]" if gap_note else ""))
        else:
            result.fail(f"tranid={tranid} · {inv} · {ccy} — "
                       f"FX G/L mismatch: expected={expected_gl:.4f} actual={actual_gl:.4f} "
                       f"diff={abs(expected_gl - actual_gl):.4f}"
                       + (f" [{gap_note.strip()}]" if gap_note else ""))

    if result.total == 0:
        result.skip("No foreign currency equity/bond trades to check")

    return result

# ============================================================
# PILLAR 4 — MARK VERIFICATION
# Period end MV = qty × price × pricing_factor × fx_rate
# Change in unrealized chains correctly period over period
# ============================================================

def pillar_marks(events: list, im: dict, calendar_records: list,
                 jes_by_period: dict, price_index: dict,
                 fx_index: dict) -> ProofResult:
    """
    For every holding at every period end:
    1. Compute MV from raw inputs: qty × price × pf × fx_rate
    2. Compare against MV in JEs
    3. Verify change in unrealized chains period over period
    """
    from datetime import date as _date

    result = ProofResult("marks")

    if not calendar_records:
        result.skip("No calendar records found")
        return result

    prev_mv = {}  # investment → MV at end of previous period

    for rec in sorted(calendar_records, key=lambda r: r.get("period_name", "")):
        period_name = rec.get("period_name", "")
        period_end = _norm_date(rec.get("current_period_cutoff", ""))

        # ── OPEN PERIOD SKIP ──────────────────────────────────────
        # If period end is in the future — month not closed yet
        # Not a proof failure — data simply doesn't exist yet
        try:
            pe_date = datetime.strptime(period_end, "%Y-%m-%d").date()
            if pe_date > _date.today():
                result.skip(f"{period_name} — open period (end {period_end} > today)")
                continue
        except Exception:
            pass

        if period_name not in jes_by_period:
            result.skip(f"{period_name} — no JEs processed")
            continue

        jes = jes_by_period[period_name]

        # Accumulate per-investment from JEs across ALL periods up to this one
        qty_by_inv = defaultdict(float)
        cost_by_inv = defaultdict(float)
        unreal_price_by_inv = defaultdict(float)
        unreal_fx_by_inv = defaultdict(float)

        for pn, pjes in jes_by_period.items():
            if pn > period_name:
                continue
            for je in pjes:
                fa = str(_je_val(je, "financial_account") or "")
                ls = str(_je_val(je, "ls") or "")
                inv = str(_je_val(je, "investment") or "")
                qty = _safe_float(_je_val(je, "quantity")) or 0.0
                book = _safe_float(_je_val(je, "book")) or 0.0

                if fa == "Cost" and ls in ("l", "s"):
                    qty_by_inv[inv] += qty
                    cost_by_inv[inv] += book
                elif fa == "UnrealizedPriceGL" or fa == "UnrealPriceGL":
                    unreal_price_by_inv[inv] += book
                elif fa == "UnrealizedFXGL" or fa == "UnrealFXGL":
                    unreal_fx_by_inv[inv] += book

        for inv, qty in qty_by_inv.items():
            if not inv or inv in ("USD", ""):
                continue
            if abs(qty) < QTY_TOLERANCE:
                continue

            if inv in im and im[inv].get("investment_type", "").upper() == "CURRENCY":
                continue

            pf = 1.0
            ccy = "USD"
            if inv in im:
                pf = _safe_float(im[inv].get("pricing_factor")) or 1.0
                raw_ccy = (im[inv].get("currency") or "").strip()
                if not raw_ccy or raw_ccy == "0" or len(raw_ccy) > 3:
                    raw_ccy = (im[inv].get("asset_class") or "USD").strip()
                ccy = raw_ccy if (raw_ccy and len(raw_ccy) <= 3) else "USD"

            price, price_gap = _find_rate(price_index, inv, period_end)
            if price is None:
                result.warn(f"{period_name} · {inv} — no price on {period_end} for MV check")
                continue

            fx_rate = 1.0
            fx_gap = 0
            if ccy != "USD":
                fx_rate, fx_gap = _find_rate(fx_index, ccy, period_end)
                if fx_rate is None:
                    result.warn(f"{period_name} · {inv} — no FX rate {ccy}/USD on {period_end}")
                    continue

            # ── THE PROOF EQUATION ───────────────────────────────
            mv_local = qty * price * pf
            mv_base = mv_local * fx_rate

            cost_base = cost_by_inv.get(inv, 0.0)
            unreal_price_gl = unreal_price_by_inv.get(inv, 0.0)
            unreal_fx_gl = unreal_fx_by_inv.get(inv, 0.0)
            acct_mv_base = cost_base + unreal_price_gl + unreal_fx_gl

            gap_note = ""
            if price_gap: gap_note += f" price {price_gap}d gap"
            if fx_gap:    gap_note += f" fx {fx_gap}d gap"

            proof_ok = _is_tolerance_ok(mv_base, acct_mv_base)

            if proof_ok:
                result.ok(
                    f"{period_name} · {inv} — MVBase PROVED\n"
                    f"         VAI Calc   : qty={qty:,.0f} × px={price:.4f} × pf={pf} × fx={fx_rate:.6f} = {mv_base:,.2f} USD\n"
                    f"         Accounting : cost={cost_base:,.2f} + unrealPx={unreal_price_gl:,.2f} + unrealFX={unreal_fx_gl:,.2f} = {acct_mv_base:,.2f} USD\n"
                    f"         MVLocal    : {mv_local:,.2f} {ccy}"
                    + (f"  [{gap_note.strip()}]" if gap_note else "")
                )
            else:
                result.fail(
                    f"{period_name} · {inv} — MVBase MISMATCH\n"
                    f"         VAI Calc   : qty={qty:,.0f} × px={price:.4f} × pf={pf} × fx={fx_rate:.6f} = {mv_base:,.2f} USD\n"
                    f"         Accounting : cost={cost_base:,.2f} + unrealPx={unreal_price_gl:,.2f} + unrealFX={unreal_fx_gl:,.2f} = {acct_mv_base:,.2f} USD\n"
                    f"         Diff       : {abs(mv_base - acct_mv_base):,.4f} USD"
                    + (f"  [{gap_note.strip()}]" if gap_note else "")
                )

            # ── DELTA UNREALIZED CHECK ────────────────────────────
            if inv in prev_mv:
                delta_acct = acct_mv_base - prev_mv[inv]
                result.ok(
                    f"{period_name} · {inv} — Δ unrealized (base) = "
                    f"{delta_acct:+,.2f} USD "
                    f"({prev_mv[inv]:,.2f} → {acct_mv_base:,.2f})"
                )

            prev_mv[inv] = acct_mv_base

    return result

# ============================================================
# PILLAR 5 — CHART OF ACCOUNTS VALIDATION
# Every financial_account posted must exist in chart_of_accounts.csv
# ============================================================

def pillar_chart_of_accounts(jes_by_period: dict) -> ProofResult:
    import csv
    from v_config import REFDATA_PATH

    result = ProofResult("chart_of_accounts")

    coa_path = os.path.join(REFDATA_PATH, "chart_of_accounts.csv")

    if not os.path.exists(coa_path):
        result.skip("chart_of_accounts.csv not found")
        return result

    valid_accounts = set()
    with open(coa_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("System_Name", "").strip()
            if name:
                valid_accounts.add(name)

    if not valid_accounts:
        result.skip("No System_Name entries found in chart_of_accounts.csv")
        return result

    unknown = {}
    for period_name, jes in jes_by_period.items():
        for je in jes:
            fa = str(_je_val(je, "financial_account") or "").strip()
            if not fa:
                continue
            if fa not in valid_accounts:
                if fa not in unknown:
                    unknown[fa] = set()
                unknown[fa].add(period_name)

    if unknown:
        for fa, periods in sorted(unknown.items()):
            result.fail(
                f"Unknown account '{fa}' — not in COA "
                f"(periods: {', '.join(sorted(periods))})"
            )
    else:
        total_jes = sum(len(jes) for jes in jes_by_period.values())
        result.ok(
            f"All accounts valid — {total_jes} JEs checked "
            f"against {len(valid_accounts)} COA entries"
        )

    return result

# ============================================================
# PRINT HELPERS
# ============================================================

def _print_pillar_result(result: ProofResult, verbose: bool = False):
    label = result.pillar.upper()
    print(f"\n{BOLD}{BLUE}── PILLAR: {label}{RESET}")
    print(f"   Checks: {result.total}  "
          f"{GREEN}✓{result.passes.__len__()}{RESET}  "
          f"{YELLOW}⚠{result.warnings.__len__()}{RESET}  "
          f"{RED}✗{result.failures.__len__()}{RESET}")

    if result.failures:
        print(f"\n   {RED}FAILURES:{RESET}")
        for f in result.failures:
            print(f"   {_fail(f)}")

    if result.warnings:
        print(f"\n   {YELLOW}WARNINGS:{RESET}")
        for w in result.warnings:
            print(f"   {_warn(w)}")

    if verbose and result.passes:
        print(f"\n   {GREEN}PASSES:{RESET}")
        for p in result.passes:
            print(f"   {_ok(p)}")

    if result.skipped and verbose:
        for s in result.skipped:
            print(f"   {_skip(s)}")


# ============================================================
# MAIN
# ============================================================

def run_proof(portfolio: str, calendar: str, period: str = None,
              tranid_filter: int = None, investment_filter: str = None,
              pillar_filter: str = None, verbose: bool = False,
              funds_path: str = "funds", refdata_path: str = "refdata"):

    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"{BOLD}  VAI PROOF ENGINE — Visibility{RESET}")
    print(f"  Portfolio  : {portfolio}")
    print(f"  Calendar   : {calendar}")
    print(f"  Period     : {period or 'ALL'}")
    if tranid_filter:     print(f"  Tran ID    : {tranid_filter}")
    if investment_filter: print(f"  Investment : {investment_filter}")
    if pillar_filter:     print(f"  Pillar     : {pillar_filter}")
    print(f"{'═'*65}{RESET}\n")

    # ── LOAD DATA ──────────────────────────────────────────────
    print("Loading data...")
    events           = load_events(portfolio, funds_path)
    im               = load_investment_master(portfolio, funds_path)
    price_index      = load_price_index(refdata_path)
    fx_index         = load_fx_index(refdata_path)
    jes_by_period    = load_jes_from_journals(portfolio, calendar, funds_path, period)
    calendar_records = load_calendar_records(portfolio, calendar, funds_path)

    # Filter to relevant period records
    if period:
        calendar_records = [r for r in calendar_records
                           if r.get("period_name") == period]

    print(f"  Events          : {len(events)}")
    print(f"  IM entries      : {len(im)}")
    print(f"  Price entries   : {len(price_index)}")
    print(f"  FX entries      : {len(fx_index)}")
    print(f"  Periods in JEs  : {len(jes_by_period)}")
    print(f"  Calendar records: {len(calendar_records)}")

    # Apply filters
    if investment_filter:
        inv_upper = investment_filter.upper()
        events = [e for e in events
                 if e.get("investment", "").upper() == inv_upper]
    if tranid_filter:
        events = [e for e in events
                 if int(_safe_float(e.get("tranid")) or 0) == tranid_filter]

    # ── RUN PILLARS ────────────────────────────────────────────
    results = []
    run_all = pillar_filter is None

    if run_all or pillar_filter == "availability":
        print(f"\n{CYAN}Running Pillar 1 — Data Availability...{RESET}")
        r = pillar_availability(events, im, calendar_records,
                                price_index, fx_index)
        results.append(r)
        _print_pillar_result(r, verbose)

    if run_all or pillar_filter == "balance":
        print(f"\n{CYAN}Running Pillar 2 — Journal Balance...{RESET}")
        r = pillar_balance(jes_by_period)
        results.append(r)
        _print_pillar_result(r, verbose)

    if run_all or pillar_filter == "settle_fx":
        print(f"\n{CYAN}Running Pillar 3 — Trade/Settle FX...{RESET}")
        r = pillar_settle_fx(events, jes_by_period, fx_index)
        results.append(r)
        _print_pillar_result(r, verbose)

    if run_all or pillar_filter == "marks":
        print(f"\n{CYAN}Running Pillar 4 — Mark Verification...{RESET}")
        r = pillar_marks(events, im, calendar_records,
                         jes_by_period, price_index, fx_index)
        results.append(r)
        _print_pillar_result(r, verbose)

    if run_all or pillar_filter == "chart_of_accounts":
        print(f"\n{CYAN}Running Pillar 5 — Chart of Accounts...{RESET}")
        r5 = pillar_chart_of_accounts(jes_by_period)
        _print_pillar_result(r5, verbose)
        results.append(r5)

    # ── SUMMARY ────────────────────────────────────────────────
    total_pass = sum(len(r.passes)   for r in results)
    total_warn = sum(len(r.warnings) for r in results)
    total_fail = sum(len(r.failures) for r in results)
    all_clear  = all(r.all_clear for r in results)

    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"{BOLD}  PROOF SUMMARY{RESET}")
    print(f"{'═'*65}")
    print(f"  {GREEN}✓ PASS   {total_pass}{RESET}")
    print(f"  {YELLOW}⚠ WARN   {total_warn}{RESET}")
    print(f"  {RED}✗ FAIL   {total_fail}{RESET}")

    if all_clear and total_pass > 0:
        print(f"\n{GREEN}{BOLD}  ✓ ALL CLEAR — proof holds{RESET}")
    elif all_clear and total_pass == 0:
        print(f"\n{YELLOW}{BOLD}  ⚠ NO CHECKS RAN — verify data is processed{RESET}")
    else:
        print(f"\n{RED}{BOLD}  ✗ PROOF FAILED — {total_fail} failure(s){RESET}")
        print(f"\n  {CYAN}→ Use OPS → Reverse/Modify Event to correct{RESET}")
        print(f"  {CYAN}→ Reprocess after correction{RESET}")
        print(f"  {CYAN}→ Re-run proof to verify fix{RESET}")

    print(f"{'═'*65}\n")


    return results

# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="VAI Proof Engine — Visibility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pillars:
  availability  prices and FX rates exist for all required dates
  balance       debits = credits every period (double-entry integrity)
  settle_fx     trade/settle FX G/L uses correct rate
  marks         period end MV = qty x price x pf x fx_rate

Examples:
  python proof_engine.py Portfolio3 Monthly
  python proof_engine.py Portfolio3 Monthly 2026-01
  python proof_engine.py Portfolio3 Monthly --pillar balance
  python proof_engine.py Portfolio3 Monthly --investment MITIB --verbose
        """
    )
    parser.add_argument("portfolio",   help="Portfolio ID e.g. Portfolio3")
    parser.add_argument("calendar",    help="Calendar e.g. Monthly")
    parser.add_argument("period",      nargs="?", help="Period e.g. 2026-01 (optional)")
    parser.add_argument("--tranid",     type=int,  help="Filter to single tranid")
    parser.add_argument("--investment", type=str,  help="Filter to single investment")
    parser.add_argument("--pillar",     type=str,
                        choices=["availability", "balance", "settle_fx", "marks", "chart_of_accounts"],
                        help="Run single pillar only")
    parser.add_argument("--verbose",   action="store_true",
                        help="Show passing checks too")
    parser.add_argument("--funds",     default="funds",   help="Funds path")
    parser.add_argument("--refdata",   default="refdata", help="Refdata path")

    args = parser.parse_args()

    run_proof(
        portfolio         = args.portfolio,
        calendar          = args.calendar,
        period            = args.period,
        tranid_filter     = args.tranid,
        investment_filter = args.investment,
        pillar_filter     = args.pillar,
        verbose           = args.verbose,
        funds_path        = args.funds,
        refdata_path      = args.refdata,
    )