# -*- coding: utf-8 -*-
"""
proof_engine.py — Visibility VAI Proof Engine
══════════════════════════════════════════════════════════════════════════════
Eight pillars. Consistent return structure. Summary and verbose modes.

Pillars:
  1. availability      prices and FX rates exist for all required dates
  2. balance           debits = credits every period (double-entry integrity)
  3. settle_fx         trade/settle FX G/L uses correct rate
  4. marks             period end MV = qty × price × pf × fx_rate
  5. chart_of_accounts every financial_account posted exists in COA
  6. data              event file integrity (kdbegin, holidays, qty, price, dupes)
  7. accrual_residual  closed positions carry no accrued residual; accrued
                       accounts touched only by declared transaction names
  8. accrual_policy    journal postings exhibit the fund's declared accrual
                       election (vocabulary, date placement, gap multiples)

Usage:
  python proof_engine.py Portfolio1 Monthly
  python proof_engine.py Portfolio1 Monthly 2024-06
  python proof_engine.py Portfolio1 Monthly --period-from 2024-01 --period-to 2024-06
  python proof_engine.py Portfolio1 Monthly --pillar marks --verbose
  python proof_engine.py Portfolio1 Monthly --pillar accrual_policy --verbose
  python proof_engine.py Portfolio1 Monthly --investment AAPL --verbose

CPH integration (optional):
  from proof_engine import run_proof_pre_cph, run_proof_post_cph

Henry J. Murphy — Chest Financial Systems
VAI — Visibility Artificial Intelligence
"""

import pickle
import csv
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timedelta, date as date_type
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from v_config import REFDATA_PATH, FUNDS_PATH

# ── Default Base- Use for now add portfolio lookup later ──────────────────────
BASE_CURRENCY = "USD"

# ── TOLERANCES ────────────────────────────────────────────────────────────────
AMOUNT_TOLERANCE = 0.01
PCT_TOLERANCE    = 0.0001
QTY_TOLERANCE    = 0.000001

# ── CONSOLE COLORS ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# ── NYSE HOLIDAYS 2019-2027 ───────────────────────────────────────────────────
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

ADJUSTMENT_METHODS = {"adjustment", "adjust"}

UNREALIZED_ACCOUNTS = {
    "MarketVal", "MarketValue",
    "UnrealizedGainLoss", "UnrealizedGL",
    "UnrealPriceGL", "UnrealFXGL",
    "UnrealPriceGLOffset", "UnrealFXGLOffset",
    "PriceGainLoss", "FXGainLoss",
    "AccruedIncome", "AmortDiscount", "AmortPremium",
}

SETTLE_FX_METHODS = {
    "buy_equity", "sell_equity", "short_equity", "cover_equity",
    "buy_bond", "sell_bond",
}

# ── ACCRUAL CONVENTION CONSTANTS (Pillars 7 and 8) ────────────────────────────
# Institutional memory of the $277.77 discovery (DOMAIN_MODEL Ch. 9).

ACCRUED_ACCOUNTS = {"AccruedInterestReceivable", "AccruedInterestPayable"}

# Transaction names allowed to post to accrued-interest accounts:
# the accrual vocabulary (per recognition policy) + known relief paths.
ACCRUAL_TXN_VOCABULARY = {
    "BondAccrual",          # own-day accrual, every policy
    "SingleDayFactor",      # gap days, dated themselves
    "MultiDayPreceding",    # gap days, stamped prior business day
    "MultiDayFollowing",    # gap days, stamped following business day
}
ACCRUED_TOUCH_ALLOWED = ACCRUAL_TXN_VOCABULARY | {
    "Settlement",           # Phase-2 reclass in / relief out
    "Coupon",               # Phase-4 relief (when coupon rule lands)
}

# Which transaction names each declared policy may produce.
POLICY_VOCAB = {
    "single_day_factor":  {"BondAccrual", "SingleDayFactor"},
    "multiday_preceding": {"BondAccrual", "MultiDayPreceding"},
    "multiday_following": {"BondAccrual", "MultiDayFollowing"},
}

# Tolerance for a "zero" residual after full close. Trade-side figures
# round to the penny (quotes in thirds), so a closed round trip can
# legitimately leave +/- a cent or two. Anything beyond this is a real
# residual -- e.g. 277.77 is two missing days, not rounding.
RESIDUAL_TOLERANCE = 0.02

# Tolerance for gap-entry amounts as multiples of the daily amount.
MULTIPLE_TOLERANCE = 0.02


# ══════════════════════════════════════════════════════════════════════════════
# PROOF RESULT — consistent structure across all pillars
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ProofItem:
    """Single check result within a pillar."""
    status:   str    # PASS | WARN | FAIL | SKIP
    severity: str    # CRITICAL | HIGH | WARNING | INFO
    message:  str
    period:   str = ""
    investment: str = ""


def _print_summary_grid(results: list):
    """
    Verdict grid — one line per pillar. The default view.

    SAFETY: a pillar that only SKIPPED (no data to check) has zero failures,
    but it is NOT a pass — it proved nothing. The engine must never report
    ALL CLEAR when it examined no data. A run where the substantive,
    data-dependent pillars all skipped is reported as NOTHING PROVEN, not
    as a clean pass. Reporting green on an empty run is worse than useless —
    it manufactures false confidence.
    """
    print(f"\n{BOLD}{'─' * 70}{RESET}")
    print(f"{BOLD}  {'PILLAR':<20}{'VERDICT':<10}{'✓':>8}{'⚠':>8}{'✗':>8}{'skip':>6}   {'CRIT':>4}{RESET}")
    print(f"  {'─' * 72}")

    any_fail = False

    # A pillar "ran" if it produced at least one real check (pass/warn/fail).
    # A pillar that only has skips examined nothing.
    def _ran(r):
        return (len(r.passes) + len(r.warnings) + len(r.failures)) > 0

    for r in results:
        if not r.all_clear:
            any_fail = True
        n_pass = len(r.passes)
        n_warn = len(r.warnings)
        n_fail = len(r.failures)
        n_skip = len(r.skipped)
        crit = f"{RED}⛔{RESET}" if r.has_critical else ""

        # Per-pillar verdict: FAIL if failures; else NOT RUN if it only skipped;
        # else PASS. "NOT RUN" is visually distinct from PASS on purpose.
        if n_fail > 0:
            vtxt, vcol = "FAIL", RED
        elif not _ran(r):
            vtxt, vcol = "NOT RUN", YELLOW
        else:
            vtxt, vcol = "PASS", GREEN

        print(f"  {r.pillar:<20}{vcol}{vtxt:<10}{RESET}"
              f"{n_pass:>8}{n_warn:>8}{n_fail:>8}{n_skip:>6}   {crit:>4}")
    print(f"  {'─' * 72}")

    # ── Honest overall verdict ────────────────────────────────────────────────
    # The substantive, data-dependent pillars. If NONE of these examined any
    # data, the run proved nothing regardless of the absence of failures.
    DATA_PILLARS = {"availability", "balance", "marks"}
    data_results = [r for r in results if r.pillar in DATA_PILLARS]
    data_ran = [r for r in data_results if _ran(r)]
    total_checks = sum(len(r.passes) + len(r.warnings) + len(r.failures)
                       for r in results)

    failed = [r.pillar for r in results if not r.all_clear]

    if any_fail:
        print(f"\n{RED}{BOLD}  ✗ {len(failed)} pillar(s) failed: {', '.join(failed)}{RESET}")
        print(f"  {DIM}  → rerun with --pillar <name> --verbose to drill in{RESET}\n")
        return

    # No failures — but did we actually CHECK anything?
    if total_checks == 0:
        print(f"\n{YELLOW}{BOLD}  ⚠ NOTHING PROVEN — the engine examined NO data.{RESET}")
        print(f"  {YELLOW}    0 checks ran across all pillars. This is NOT an all-clear.{RESET}")
        print(f"  {DIM}    Likely cause: no journals/periods loaded for this portfolio+calendar.{RESET}")
        print(f"  {DIM}    Check that processing (CPH) has run and that the calendar name is correct.{RESET}\n")
        return

    if not data_ran:
        # Some pillar ran (e.g. chart_of_accounts on an empty book) but every
        # data-dependent pillar skipped — still hollow.
        skipped_names = ", ".join(r.pillar for r in data_results if not _ran(r))
        print(f"\n{YELLOW}{BOLD}  ⚠ NOTHING PROVEN ON POSITIONS — data pillars examined no data.{RESET}")
        print(f"  {YELLOW}    No data checked by: {skipped_names}.{RESET}")
        print(f"  {YELLOW}    This is NOT a clean book — it is an unexamined one.{RESET}")
        print(f"  {DIM}    Likely cause: no periods/journals loaded. Confirm CPH ran and the{RESET}")
        print(f"  {DIM}    calendar/portfolio names match what's on disk.{RESET}\n")
        return

    # Genuine all-clear: no failures AND the data pillars actually examined data.
    n_data_checks = sum(len(r.passes) + len(r.warnings) + len(r.failures)
                        for r in data_ran)
    print(f"\n{GREEN}{BOLD}  ✓ ALL CLEAR{RESET}  "
          f"{DIM}{total_checks} checks across {len(results)} pillars "
          f"({n_data_checks} on positions/periods){RESET}\n")


class ProofResult:
    """
    Consistent return structure for all pillars.
    Summary: counts only.
    Verbose: full item list.
    """
    def __init__(self, pillar: str):
        self.pillar  = pillar
        self.items:  list[ProofItem] = []

    # ── Convenience adders ────────────────────────────────────────────────────
    def ok(self,   msg, period="", investment="", severity="INFO"):
        self.items.append(ProofItem("PASS", severity, msg, period, investment))

    def warn(self, msg, period="", investment="", severity="WARNING"):
        self.items.append(ProofItem("WARN", severity, msg, period, investment))

    def fail(self, msg, period="", investment="", severity="HIGH"):
        self.items.append(ProofItem("FAIL", severity, msg, period, investment))

    def critical(self, msg, period="", investment=""):
        self.items.append(ProofItem("FAIL", "CRITICAL", msg, period, investment))

    def skip(self, msg, period="", investment=""):
        self.items.append(ProofItem("SKIP", "INFO", msg, period, investment))

    # ── Aggregates ────────────────────────────────────────────────────────────
    @property
    def passes(self):   return [i for i in self.items if i.status == "PASS"]
    @property
    def warnings(self): return [i for i in self.items if i.status == "WARN"]
    @property
    def failures(self): return [i for i in self.items if i.status == "FAIL"]
    @property
    def skipped(self):  return [i for i in self.items if i.status == "SKIP"]
    @property
    def criticals(self): return [i for i in self.items if i.severity == "CRITICAL"]
    @property
    def all_clear(self): return len(self.failures) == 0
    @property
    def has_critical(self): return len(self.criticals) > 0
    @property
    def total(self): return len(self.items)

    def summary(self) -> dict:
        """Clean summary dict for API/UI consumption."""
        return {
            "pillar":       self.pillar,
            "all_clear":    self.all_clear,
            "has_critical": self.has_critical,
            "passes":       len(self.passes),
            "warnings":     len(self.warnings),
            "failures":     len(self.failures),
            "skipped":      len(self.skipped),
        }

    def to_dict(self, verbose: bool = False) -> dict:
        """Full dict for API/UI consumption."""
        d = self.summary()
        if verbose:
            d["items"] = [
                {
                    "status":     i.status,
                    "severity":   i.severity,
                    "message":    i.message,
                    "period":     i.period,
                    "investment": i.investment,
                }
                for i in self.items
                if i.status != "PASS" or verbose
            ]
        else:
            # Non-verbose: only failures and warnings
            d["failure_list"] = [i.message for i in self.failures]
            d["warning_list"] = [i.message for i in self.warnings]
        return d


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _is_business_day(d: str) -> bool:
    try:
        dt = datetime.strptime(d, "%Y-%m-%d").date()
        return dt.weekday() < 5 and dt not in US_HOLIDAYS
    except Exception:
        return True

def _is_holiday_or_weekend(d: date_type) -> bool:
    return d.weekday() >= 5 or d in US_HOLIDAYS

def _is_adjustment(method: str) -> bool:
    return str(method).lower().strip() in ADJUSTMENT_METHODS

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

def _parse_event_date(date_str: str) -> Optional[date_type]:
    try:
        return datetime.strptime(_norm_date(str(date_str)), "%Y-%m-%d").date()
    except:
        return None

def _safe_float(val) -> Optional[float]:
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def _je_val(je, field: str):
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

def _je_date_obj(je, field: str) -> Optional[date_type]:
    """Date object from a JE field, or None. For calendar arithmetic."""
    s = _je_date(je, field)
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def _find_rate(index: dict, key_prefix: str, date: str,
               tolerance_days: int = 5) -> tuple:
    if (key_prefix, date) in index:
        return index[(key_prefix, date)], 0
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        search_order = [-1] if not _is_business_day(date) else [-1, 1]
        for days in range(1, tolerance_days + 1):
            for sign in search_order:
                d = (dt + timedelta(days=days * sign)).strftime("%Y-%m-%d")
                if (key_prefix, d) in index:
                    return index[(key_prefix, d)], days
    except Exception:
        pass
    return None, None

def _active_events(events: list) -> list:
    return [e for e in events
            if e.get("kdend", "12/31/2099:00:00:00") == "12/31/2099:00:00:00"]

def _is_tolerance_ok(a: float, b: float) -> bool:
    diff = abs(a - b)
    if diff <= AMOUNT_TOLERANCE:
        return True
    base = max(abs(a), abs(b), 1.0)
    return (diff / base) <= PCT_TOLERANCE

def _filter_periods(jes_by_period: dict,
                    period: str = None,
                    period_from: str = None,
                    period_to: str = None) -> dict:
    """Filter jes_by_period to requested range."""
    if period:
        return {k: v for k, v in jes_by_period.items() if k == period}
    if period_from or period_to:
        result = {}
        for k, v in jes_by_period.items():
            if period_from and k < period_from:
                continue
            if period_to and k > period_to:
                continue
            result[k] = v
        return result
    return jes_by_period


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADERS
# ══════════════════════════════════════════════════════════════════════════════

def load_events(portfolio: str, funds_path: str) -> list:
    path = Path(funds_path) / portfolio / "Events" / f"{portfolio}.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def load_investment_master(portfolio: str, funds_path: str) -> dict:
    path = Path(funds_path) / portfolio / "RefData" / "investment_master.csv"
    if not path.exists():
        # Try global refdata
        path = Path(REFDATA_PATH) / "investment_master.csv"
    if not path.exists():
        return {}
    result = {}
    with open(path, newline="", encoding="cp1252") as f:
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
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("symbol") or row.get("ticker") or
                      row.get("investment") or "").strip()
            date   = _norm_date(row.get("date") or row.get("price_date") or "")
            price  = _safe_float(row.get("price") or row.get("close") or "")
            if ticker and date and price is not None:
                index[(ticker, date)] = price
    return index

def load_fx_index(refdata_path: str) -> dict:
    path = Path(refdata_path) / "fx_master.csv"
    if not path.exists():
        return {}
    index = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            ccy  = (row.get("currency") or row.get("ticker") or "").strip()
            date = _norm_date(row.get("date") or row.get("fx_date") or "")
            rate = _safe_float(row.get("rate") or row.get("price") or
                               row.get("close") or "")
            if ccy and date and rate is not None:
                index[(ccy, date)] = rate
    return index


def load_jes_from_journals(portfolio: str, calendar: str,
                           funds_path: str,
                           period: str = None):
    """
    Returns TWO dicts:
      jes_by_period  {period_name: [journals]} -- regular pkl
                     overwrites adjusting for the same period
                     (alphabetical load order; regular is the
                     authoritative pass-2 output)
      period_meta    {pkl_filename: {period_name,
                                     precedence_version,
                                     precedence_fingerprint}}
                     -- one entry per FILE, so adjusting and
                     regular stamps are both visible to Pillar 9
    """
    journals_dir = (Path(funds_path) / portfolio / "Calendars" /
                    calendar / "Journals")
    result = {}
    meta = {}
    if not journals_dir.exists():
        return result, meta
    for pkl_file in sorted(journals_dir.glob("*.pkl")):
        try:
            with open(pkl_file, "rb") as f:
                data = pickle.load(f)
            if not isinstance(data, dict):
                continue
            period_name = data.get("period_name", pkl_file.stem)
            jes = data.get("journals", [])
            if period and period_name != period:
                continue
            result[period_name] = jes
            meta[pkl_file.name] = {
                "period_name": period_name,
                "precedence_version": data.get("precedence_version"),
                "precedence_fingerprint": data.get("precedence_fingerprint"),
            }
        except Exception as e:
            print(f"  WARNING: Could not read {pkl_file.name}: {e}")
    return result, meta

def load_calendar_records(portfolio: str, calendar: str,
                          funds_path: str) -> list:
    import json
    cal_path = (Path(funds_path) / portfolio / "Calendars" /
                calendar / f"{calendar}.txt")
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


# ══════════════════════════════════════════════════════════════════════════════
# PILLAR 1 — DATA AVAILABILITY
# ══════════════════════════════════════════════════════════════════════════════

def pillar_availability(events, im, calendar_records,
                        price_index, fx_index) -> ProofResult:
    result = ProofResult("availability")
    active = _active_events(events)

    holdings = {}
    for e in active:
        inv = e.get("investment", "")
        ccy = e.get("payment_currency", "USD")
        if inv and inv not in holdings:
            if inv in im:
                ccy = im[inv].get("currency", ccy) or ccy
            holdings[inv] = ccy

    period_end_dates = []
    for rec in calendar_records:
        cutoff = _norm_date(rec.get("current_period_cutoff", ""))
        if cutoff:
            period_end_dates.append(cutoff)

    checked_prices = set()
    for inv, ccy in holdings.items():
        if inv in im and im[inv].get("investment_type", "").upper() == "CURRENCY":
            continue
        for period_end in period_end_dates:
            key = (inv, period_end)
            if key in checked_prices:
                continue
            checked_prices.add(key)
            price, gap = _find_rate(price_index, inv, period_end)
            if price is None:
                result.fail(f"Price missing: {inv} on {period_end}",
                           period=period_end, investment=inv)
            elif gap and gap > 0 and _is_business_day(period_end):
                result.warn(f"Price gap: {inv} on {period_end} — {gap}d",
                           period=period_end, investment=inv)
            else:
                result.ok(f"Price exists: {inv} on {period_end}",
                         period=period_end, investment=inv)

    checked_fx = set()
    foreign_methods = {
        "buy_equity", "sell_equity", "short_equity", "cover_equity",
        "buy_bond", "sell_bond", "deposit_currency", "withdraw_currency", "spot_fx"
    }
    for e in active:
        method = e.get("method", "")
        ccy    = e.get("payment_currency", "USD")
        settle = _norm_date(e.get("settledate", ""))
        tranid = e.get("tranid", "?")
        inv    = e.get("investment", "")
        if ccy == "USD" or method not in foreign_methods or not settle:
            continue
        key = (ccy, settle)
        if key in checked_fx:
            continue
        checked_fx.add(key)
        rate, gap = _find_rate(fx_index, ccy, settle)
        if rate is None:
            result.fail(f"FX missing: {ccy}/USD on {settle} (tranid={tranid} {inv})",
                       period=settle, investment=inv)
        elif gap and gap > 0:
            result.warn(f"FX gap: {ccy}/USD on {settle} — {gap}d",
                       period=settle, investment=inv)
        else:
            result.ok(f"FX exists: {ccy}/USD on {settle}",
                     period=settle, investment=inv)

    if result.total == 0:
        result.skip("No holdings or period dates to check")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PILLAR 2 — JOURNAL BALANCE
# ══════════════════════════════════════════════════════════════════════════════

def pillar_balance(jes_by_period) -> ProofResult:
    """
    Verify all JEs balance per tranID (local and book each sum to ~0 per tran).
    Excludes UNREALIZED_ACCOUNTS (e.g. MarketVal — single-sided stat entries).
    Reports failures by tranID so the offending transaction is identifiable.
    """
    result = ProofResult("balance")
    for period_name, jes in sorted(jes_by_period.items()):
        # tranid -> [local_sum, book_sum, je_count]
        by_tran = defaultdict(lambda: [0.0, 0.0, 0])
        no_tranid = []   # JEs missing tranid — flagged individually
        excluded = 0

        for je in jes:
            fa = str(_je_val(je, "financial_account") or "")
            if any(u.lower() in fa.lower() for u in UNREALIZED_ACCOUNTS):
                excluded += 1
                continue
            tranid_raw = _je_val(je, "tranid")
            if tranid_raw is None or str(tranid_raw).strip() == "":
                no_tranid.append(fa)
                continue
            tranid = str(tranid_raw)
            by_tran[tranid][0] += _safe_float(_je_val(je, "local")) or 0.0
            by_tran[tranid][1] += _safe_float(_je_val(je, "book"))  or 0.0
            by_tran[tranid][2] += 1

        # Flag missing-tranid JEs (data integrity, separate from balance math)
        for fa in no_tranid:
            result.fail(f"{period_name} — JE missing tranID "
                        f"(financial_account={fa!r})",
                        period=period_name)

        if not by_tran:
            if not no_tranid:
                result.skip(f"{period_name} — no balancing JEs to check "
                            f"(excluded {excluded} stat entries)",
                            period=period_name)
            continue

        # Per-tranID balance check
        failing = []
        for tranid, (l_sum, b_sum, n) in by_tran.items():
            if abs(l_sum) > AMOUNT_TOLERANCE or abs(b_sum) > AMOUNT_TOLERANCE:
                failing.append((tranid, l_sum, b_sum, n))

        if not failing:
            total_jes = sum(n for _, _, n in by_tran.values())
            result.ok(f"{period_name} — {len(by_tran)} tranIDs balance "
                      f"({total_jes} JEs, {excluded} stat entries excluded)",
                      period=period_name)
        else:
            # Sorted for deterministic output
            for tranid, l_sum, b_sum, n in sorted(failing, key=lambda x: x[0]):
                parts = []
                if abs(l_sum) > AMOUNT_TOLERANCE:
                    parts.append(f"LOCAL={l_sum:.4f}")
                if abs(b_sum) > AMOUNT_TOLERANCE:
                    parts.append(f"BOOK={b_sum:.4f}")
                result.fail(f"{period_name} — tranID {tranid} out of balance "
                            f"({n} JEs): {'; '.join(parts)}",
                            period=period_name)

    if result.total == 0:
        result.skip("No periods processed")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PILLAR 3 — TRADE/SETTLE FX
# ══════════════════════════════════════════════════════════════════════════════

def pillar_settle_fx(events, jes_by_period, fx_index) -> ProofResult:
    result = ProofResult("settle_fx")
    jes_by_tranid = defaultdict(list)
    for jes in jes_by_period.values():
        for je in jes:
            tid = _je_val(je, "tranid")
            if tid is not None:
                jes_by_tranid[int(tid)].append(je)

    active = _active_events(events)
    for event in active:
        method   = event.get("method", "")
        ccy      = event.get("payment_currency", "USD")
        tranid   = int(_safe_float(event.get("tranid")) or 0)
        inv      = event.get("investment", "")
        local    = _safe_float(event.get("total_amount"))
        trade_d  = _norm_date(event.get("tradedate", ""))
        settle_d = _norm_date(event.get("settledate", ""))

        if method not in SETTLE_FX_METHODS or ccy == "USD":
            continue
        if trade_d == settle_d:
            result.skip(f"tranid={tranid} {inv} — same day settle",
                       investment=inv)
            continue
        if local is None:
            result.warn(f"tranid={tranid} {inv} — missing local amount",
                       investment=inv)
            continue

        trade_book = _safe_float(event.get("total_amount_base"))
        if trade_book is None:
            result.warn(f"tranid={tranid} {inv} — missing total_amount_base",
                       investment=inv)
            continue

        settle_rate, settle_gap = _find_rate(fx_index, ccy, settle_d)
        if settle_rate is None:
            result.warn(f"tranid={tranid} {inv} — no FX rate {ccy} on {settle_d}",
                       investment=inv)
            continue

        settle_book  = abs(local) * settle_rate
        expected_gl  = settle_book - abs(trade_book)
        actual_gl    = None

        for je in jes_by_tranid.get(tranid, []):
            fa          = str(_je_val(je, "financial_account") or "")
            transaction = str(_je_val(je, "transaction") or "")
            ibor        = _je_date(je, "ibor_date")
            if fa == "FXGainTradeSettle" and transaction == "Settlement" and ibor == settle_d:
                actual_gl = _safe_float(_je_val(je, "book"))
                break

        if actual_gl is None:
            result.warn(f"tranid={tranid} {inv} — no FXGainTradeSettle JE on {settle_d}",
                       investment=inv)
            continue

        if _is_tolerance_ok(expected_gl, actual_gl):
            result.ok(f"tranid={tranid} {inv} {ccy} — FX G/L correct "
                     f"expected={expected_gl:.4f} actual={actual_gl:.4f}",
                     investment=inv)
        else:
            result.fail(f"tranid={tranid} {inv} {ccy} — FX G/L mismatch "
                       f"expected={expected_gl:.4f} actual={actual_gl:.4f} "
                       f"diff={abs(expected_gl-actual_gl):.4f}",
                       investment=inv)

    if result.total == 0:
        result.skip("No foreign currency trades to check")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PILLAR 4 — MARK VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════

def pillar_marks(events, im, calendar_records, jes_by_period,
                 price_index, fx_index) -> ProofResult:
    result = ProofResult("marks")
    if not calendar_records:
        result.skip("No calendar records")
        return result

    prev_mv = {}

    for rec in sorted(calendar_records, key=lambda r: r.get("period_name", "")):
        period_name = rec.get("period_name", "")
        period_end  = _norm_date(rec.get("current_period_cutoff", ""))

        try:
            pe_date = datetime.strptime(period_end, "%Y-%m-%d").date()
            if pe_date > date_type.today():
                result.skip(f"{period_name} — open period", period=period_name)
                continue
        except Exception:
            pass

        if period_name not in jes_by_period:
            result.skip(f"{period_name} — no JEs", period=period_name)
            continue

        qty_by_inv          = defaultdict(float)
        cost_by_inv         = defaultdict(float)
        unreal_price_by_inv = defaultdict(float)
        unreal_fx_by_inv    = defaultdict(float)

        for pn, pjes in jes_by_period.items():
            if pn > period_name:
                continue
            for je in pjes:
                fa   = str(_je_val(je, "financial_account") or "")
                ls   = str(_je_val(je, "ls") or "")
                inv  = str(_je_val(je, "investment") or "")
                qty  = _safe_float(_je_val(je, "quantity")) or 0.0
                book = _safe_float(_je_val(je, "book")) or 0.0
                if fa == "Cost" and ls in ("l", "s"):
                    qty_by_inv[inv]  += qty
                    cost_by_inv[inv] += book
                elif fa in ("UnrealizedPriceGL", "UnrealPriceGL"):
                    unreal_price_by_inv[inv] += book
                elif fa in ("UnrealizedFXGL", "UnrealFXGL"):
                    unreal_fx_by_inv[inv] += book

        for inv, qty in qty_by_inv.items():
            if not inv or inv in ("USD", "") or abs(qty) < QTY_TOLERANCE:
                continue
            if inv in im and im[inv].get("investment_type", "").upper() == "CURRENCY":
                continue

            pf  = _safe_float(im.get(inv, {}).get("pricing_factor")) or 1.0
            ccy = "USD"
            if inv in im:
                raw_ccy = (im[inv].get("currency") or "").strip()
                ccy = raw_ccy if (raw_ccy and len(raw_ccy) <= 3 and raw_ccy != "0") else "USD"

            price, price_gap = _find_rate(price_index, inv, period_end)
            if price is None:
                result.warn(f"{period_name} {inv} — no price for MV check",
                           period=period_name, investment=inv)
                continue

            fx_rate, fx_gap = (1.0, 0) if ccy == "USD" else _find_rate(fx_index, ccy, period_end)
            if fx_rate is None:
                result.warn(f"{period_name} {inv} — no FX {ccy} for MV check",
                           period=period_name, investment=inv)
                continue

            mv_local    = qty * price * pf
            mv_base     = mv_local * fx_rate
            cost_base   = cost_by_inv.get(inv, 0.0)
            unreal_px   = unreal_price_by_inv.get(inv, 0.0)
            unreal_fx   = unreal_fx_by_inv.get(inv, 0.0)
            acct_mv     = cost_base + unreal_px + unreal_fx

            if _is_tolerance_ok(mv_base, acct_mv):
                result.ok(
                    f"{period_name} · {inv} — MVBase PROVED "
                    f"VAI={mv_base:,.2f} Acct={acct_mv:,.2f}",
                    period=period_name, investment=inv
                )
            else:
                result.fail(
                    f"{period_name} · {inv} — MVBase MISMATCH\n"
                    f"         VAI Calc   : qty={qty:,.0f} × px={price:.4f} × pf={pf} × fx={fx_rate:.6f} = {mv_base:,.2f} USD\n"
                    f"         Accounting : cost={cost_base:,.2f} + unrealPx={unreal_px:,.2f} + unrealFX={unreal_fx:,.2f} = {acct_mv:,.2f} USD\n"
                    f"         Diff       : {abs(mv_base-acct_mv):,.4f} USD",
                    period=period_name, investment=inv
                )
            prev_mv[inv] = acct_mv

    return result


# ══════════════════════════════════════════════════════════════════════════════
# PILLAR 5 — CHART OF ACCOUNTS
# ══════════════════════════════════════════════════════════════════════════════

def pillar_chart_of_accounts(jes_by_period) -> ProofResult:
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
        result.skip("No System_Name entries in COA")
        return result

    unknown = {}
    for period_name, jes in jes_by_period.items():
        for je in jes:
            fa = str(_je_val(je, "financial_account") or "").strip()
            if fa and fa not in valid_accounts:
                if fa not in unknown:
                    unknown[fa] = set()
                unknown[fa].add(period_name)

    if unknown:
        for fa, periods in sorted(unknown.items()):
            result.fail(f"Unknown account '{fa}' (periods: {', '.join(sorted(periods))})")
    else:
        total = sum(len(v) for v in jes_by_period.values())
        result.ok(f"All accounts valid — {total} JEs vs {len(valid_accounts)} COA entries")
    return result

# ══════════════════════════════════════════════════════════════════════════════
# PILLAR 6 — DATA INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════

def pillar_data(events: list, jes_by_period: dict = None,
                im: dict = None) -> ProofResult:
    """
    EVENT CHECKS (read the event file):
      D-001  kdbegin must equal tradedate for non-adjustment events
      D-002  kdbegin must never be before tradedate
      D-003  tradedate must not fall on NYSE holiday or weekend
      D-004  settledate must not be before tradedate
      D-007  quantity not zero for buy/sell events
      D-008  price not zero/negative for buy/sell events
      D-009  total_amount = qty x price (instrument-aware) within tolerance

    JOURNAL CHECKS (read materialized journals, if provided):
      D-005  no duplicate journal entries
      D-006  MarketVal non-zero for active cost positions

    (D-010 contract_size/pricing_factor sanity -- parked, commented below.)
    """
    result = ProofResult("data")

    # ══════════════════════════════════════════════════════════════
    # EVENT CHECKS
    # ══════════════════════════════════════════════════════════════

    # ── D-001 kdbegin = tradedate ─────────────────────────────────
    d001 = 0
    for e in events:
        if _is_adjustment(e.get('method', '')):
            continue
        td = _parse_event_date(e.get('tradedate', ''))
        kb = _parse_event_date(e.get('kdbegin', ''))
        if td and kb and kb != td:
            d001 += 1
            if d001 <= 5:
                result.critical(
                    f"D-001 kdbegin≠tradedate: {e.get('investment','?')} "
                    f"trade={td} kdbegin={kb}",
                    investment=e.get('investment', '')
                )
    if d001 == 0:
        result.ok("D-001 kdbegin = tradedate — all clear")
    elif d001 > 5:
        result.critical(f"D-001 kdbegin≠tradedate — {d001} total violations (showing first 5)")

    # ── D-002 kdbegin not before tradedate ────────────────────────
    d002 = 0
    for e in events:
        td = _parse_event_date(e.get('tradedate', ''))
        kb = _parse_event_date(e.get('kdbegin', ''))
        if td and kb and kb < td:
            d002 += 1
            if d002 <= 5:
                result.critical(
                    f"D-002 kdbegin<tradedate: {e.get('investment','?')} "
                    f"kdbegin={kb} trade={td}",
                    investment=e.get('investment', '')
                )
    if d002 == 0:
        result.ok("D-002 kdbegin never before tradedate — all clear")
    elif d002 > 5:
        result.critical(f"D-002 kdbegin<tradedate — {d002} total (showing first 5)")

    # ── D-003 no holiday/weekend tradedates ───────────────────────
    d003 = 0
    for e in events:
        method = str(e.get('method', '')).lower()
        if 'split' in method or 'dividend' in method:
            continue
        td = _parse_event_date(e.get('tradedate', ''))
        if td and _is_holiday_or_weekend(td):
            d003 += 1
            if d003 <= 5:
                result.fail(
                    f"D-003 holiday tradedate: {e.get('investment','?')} {td}",
                    investment=e.get('investment', ''),
                    severity="HIGH"
                )
    if d003 == 0:
        result.ok("D-003 no holiday/weekend tradedates — all clear")
    elif d003 > 5:
        result.fail(f"D-003 holiday tradedates — {d003} total (showing first 5)",
                   severity="HIGH")

    # ── D-004 settle not before trade ─────────────────────────────
    d004 = 0
    for e in events:
        td = _parse_event_date(e.get('tradedate', ''))
        sd = _parse_event_date(e.get('settledate', ''))
        if td and sd and sd < td:
            d004 += 1
            if d004 <= 5:
                result.critical(
                    f"D-004 settle<trade: {e.get('investment','?')} "
                    f"settle={sd} trade={td}",
                    investment=e.get('investment', '')
                )
    if d004 == 0:
        result.ok("D-004 settledate never before tradedate — all clear")
    elif d004 > 5:
        result.critical(f"D-004 settle<trade — {d004} total (showing first 5)")

    # ── D-007 qty not zero ────────────────────────────────────────
    d007 = 0
    for e in events:
        method = str(e.get('method', '')).lower()
        if 'buy' not in method and 'sell' not in method:
            continue
        try:
            qty = float(str(e.get('quantity', 0)).strip() or 0)
            if qty == 0:
                d007 += 1
                if d007 <= 5:
                    result.critical(
                        f"D-007 zero qty: {e.get('investment','?')} "
                        f"method={method} tranid={e.get('tranid','')}",
                        investment=e.get('investment', '')
                    )
        except:
            pass
    if d007 == 0:
        result.ok("D-007 no zero quantities — all clear")
    elif d007 > 5:
        result.critical(f"D-007 zero quantities — {d007} total (showing first 5)")

    # ── D-008 price not zero/negative ─────────────────────────────
    d008 = 0
    for e in events:
        method = str(e.get('method', '')).lower()
        if 'buy' not in method and 'sell' not in method:
            continue
        try:
            price = float(str(e.get('price', 0)).strip() or 0)
            if price <= 0:
                d008 += 1
                if d008 <= 5:
                    result.critical(
                        f"D-008 zero/neg price: {e.get('investment','?')} "
                        f"price={price} tranid={e.get('tranid','')}",
                        investment=e.get('investment', '')
                    )
        except:
            pass
    if d008 == 0:
        result.ok("D-008 no zero/negative prices — all clear")
    elif d008 > 5:
        result.critical(f"D-008 zero/neg prices — {d008} total (showing first 5)")

    # ── D-009 total_amount = qty x price (instrument-aware) ──────
    # Equities: expected = qty * price. Bonds quote per-100 face:
    # expected = qty * price / 100 * pf.
    # TODO(register): replace this branch with a universal formula
    # driven entirely by instrument data (quotation basis declared
    # in the IM) once per-100 lives there, not here.
    d009 = 0
    for e in events:
        method = str(e.get('method', '')).lower()
        if 'buy' not in method and 'sell' not in method:
            continue
        try:
            qty      = float(str(e.get('quantity', 0)).strip() or 0)
            price    = float(str(e.get('price', 0)).strip() or 0)
            total    = float(str(e.get('total_amount', 0)).strip() or 0)
            inv      = str(e.get('investment', '') or '')
            inv_type = ""
            pf       = 1.0
            cs       = 1.0
            if im and inv in im:
                inv_type = str(im[inv].get('investment_type', '') or '').upper()
                pf       = _safe_float(im[inv].get('pricing_factor')) or 1.0
                cs       = _safe_float(im[inv].get('contract_size')) or 1.0

            # Universal: quotation convention lives in the IM's
            # pricing_factor (bond rows carry 0.01 = per-100).
            # No per-instrument branch; the data declares it.
            expected = abs(qty * price * pf * cs)
            actual = abs(total)
            if expected > 0 and abs(expected - actual) / expected > 0.02:
                d009 += 1
                if d009 <= 5:
                    result.fail(
                        f"D-009 amount mismatch: {e.get('investment','?')} "
                        f"qty×px={expected:.2f} total={actual:.2f}",
                        investment=e.get('investment', ''),
                        severity="HIGH"
                    )
        except:
            pass
    if d009 == 0:
        result.ok("D-009 total_amount agrees with qty×price — all clear")
    elif d009 > 5:
        result.fail(f"D-009 amount mismatches — {d009} total (showing first 5)",
                   severity="HIGH")

    # # ── D-010 contract_size and pricing_factor never zero in IM ──
    # # (Parked. Re-enable when IM hygiene checks come into scope.)
    # if im:
    #     d010 = 0
    #     for inv, attrs in im.items():
    #         cs = _safe_float(attrs.get('contract_size'))
    #         pf = _safe_float(attrs.get('pricing_factor'))
    #         if cs is not None and cs == 0:
    #             d010 += 1
    #             if d010 <= 5:
    #                 result.critical(f"D-010 contract_size=0 in IM: {inv}",
    #                                 investment=inv)
    #         if pf is not None and pf == 0:
    #             d010 += 1
    #             if d010 <= 5:
    #                 result.critical(f"D-010 pricing_factor=0 in IM: {inv}",
    #                                 investment=inv)
    #     if d010 == 0:
    #         result.ok("D-010 contract_size and pricing_factor never zero — all clear")
    #     elif d010 > 5:
    #         result.critical(f"D-010 zero multiplicative factors — {d010} total (showing first 5)")
    # else:
    #     result.skip("D-010 — no investment master provided")

    # ══════════════════════════════════════════════════════════════
    # JOURNAL CHECKS (only when journals are provided)
    # ══════════════════════════════════════════════════════════════
    if jes_by_period:
        all_jes = [je for jes in jes_by_period.values() for je in jes]

        # ── D-005 no duplicate JEs ────────────────────────────────
        seen = {}
        dupes = 0
        for je in all_jes:
            # Key includes tradedate (the entry's EFFECTIVE calendar
            # day) and transaction name: under single_day_factor a
            # weekend catch-up legitimately posts several identical
            # amounts in one processing run, distinguished only by
            # their effective dates. Same ibor_date + same amount is
            # not duplication; same EFFECTIVE day twice is.
            key = (
                str(_je_val(je, "investment") or ""),
                str(_je_date(je, "ibor_date")),
                str(_je_date(je, "tradedate")),
                str(_je_val(je, "transaction") or ""),
                str(_je_val(je, "financial_account") or ""),
                str(_je_val(je, "quantity") or ""),
                str(_je_val(je, "local") or ""),
            )
            if key in seen:
                dupes += 1
                if dupes <= 5:
                    result.fail(
                        f"D-005 duplicate JE: {key[0]} ibor={key[1]} "
                        f"trade={key[2]} txn={key[3]} {key[4]} "
                        f"qty={key[5]} local={key[6]}",
                        severity="HIGH"
                    )
            else:
                seen[key] = True
        if dupes == 0:
            result.ok(f"D-005 no duplicate JEs — {len(all_jes)} JEs checked")
        elif dupes > 5:
            result.fail(f"D-005 duplicate JEs — {dupes} total (showing first 5)",
                       severity="HIGH")

        # ── D-006 MarketVal non-zero for active positions ─────────
        mv_issues = 0
        by_inv_date = defaultdict(lambda: {"cost_qty": 0.0, "mv": 0.0})
        for je in all_jes:
            fa  = str(_je_val(je, "financial_account") or "")
            inv = str(_je_val(je, "investment") or "")
            dt  = str(_je_date(je, "ibor_date"))
            k   = (inv, dt)
            if fa == "Cost":
                qty = _safe_float(_je_val(je, "quantity")) or 0.0
                by_inv_date[k]["cost_qty"] += qty
            elif fa == "MarketVal":
                local = _safe_float(_je_val(je, "local")) or 0.0
                by_inv_date[k]["mv"] += local

        for (inv, dt), vals in by_inv_date.items():
            # Base-currency cash has no FX mark — nothing to mark
            # against the unit of account. Skip it. (Today base =
            # USD; when firms run other base currencies this should
            # read the portfolio's base ccy, not a literal.)
            if inv == BASE_CURRENCY:
                continue
            if vals["cost_qty"] != 0 and vals["mv"] == 0:
                mv_issues += 1
                if mv_issues <= 5:
                    result.fail(
                        f"D-006 MarketVal=0 for active position: "
                        f"{inv} on {dt} cost_qty={vals['cost_qty']:.0f}",
                        investment=inv,
                        severity="HIGH"
                    )
        if mv_issues == 0:
            result.ok("D-006 MarketVal non-zero for all active positions — all clear")
        elif mv_issues > 5:
            result.fail(f"D-006 MarketVal=0 issues — {mv_issues} total (showing first 5)",
                       severity="HIGH")

    return result
# ══════════════════════════════════════════════════════════════════════════════
# PILLAR 7 — ACCRUAL RESIDUAL
# ══════════════════════════════════════════════════════════════════════════════
# Institutional memory of the $277.77 discovery (DOMAIN_MODEL Ch. 9).
#
#   1. RESIDUAL-FREE CLOSES: for every (investment, location, ls) whose
#      position quantity has returned to zero across the examined span
#      (a full close), the AccruedInterestReceivable/Payable balance must
#      also be ~zero. A surviving residual means two code paths disagreed
#      about day counts, a recognition policy was mis-executed, or the
#      processing order was disturbed. A standing convention-mismatch
#      detector.
#
#   2. TRANSACTION-NAME VOCABULARY: every JE posted to an accrued-interest
#      account carries a transaction name from the declared accrual
#      vocabulary (or a known relief path: Settlement / Coupon). An
#      unknown name on an accrued account means a new code path is
#      touching the balance without declaring itself -- the
#      key-fragmentation failure mode.
#
# FIELD NAMES used: investment, location, ls, financial_account,
# quantity, local, book, transaction.

def pillar_accrual_residual(jes_by_period) -> ProofResult:
    """
    Residual-free closes + accrued-account vocabulary.

    Accumulates position quantity (Cost) and accrued-interest balances
    per (investment, location, ls) across ALL periods in chronological
    order, then asserts: closed position => zero accrued balance. Open
    positions carry accrued legitimately and report as passes.
    """
    result = ProofResult("accrual_residual")

    # (investment, location, ls) -> accumulators
    qty_by_key   = defaultdict(float)   # Cost quantity (position)
    accr_local   = defaultdict(float)   # accrued local balance
    accr_book    = defaultdict(float)   # accrued book balance
    saw_accrued  = set()                # keys that ever had accrued
    bad_txn      = []                   # vocabulary violations
    examined_jes = 0

    for period_name, jes in sorted(jes_by_period.items()):
        for je in jes:
            fa  = str(_je_val(je, "financial_account") or "")
            inv = str(_je_val(je, "investment") or "")
            loc = str(_je_val(je, "location") or "")
            ls  = str(_je_val(je, "ls") or "")
            key = (inv, loc, ls)

            if fa == "Cost":
                qty_by_key[key] += _safe_float(_je_val(je, "quantity")) or 0.0
                examined_jes += 1

            elif fa in ACCRUED_ACCOUNTS:
                accr_local[key] += _safe_float(_je_val(je, "local")) or 0.0
                accr_book[key]  += _safe_float(_je_val(je, "book"))  or 0.0
                saw_accrued.add(key)
                examined_jes += 1

                txn = str(_je_val(je, "transaction") or "")
                if txn not in ACCRUED_TOUCH_ALLOWED:
                    bad_txn.append((period_name, key, txn, fa))

    if examined_jes == 0:
        result.skip("No Cost or accrued-interest JEs to examine")
        return result

    # ── CHECK 1: residual-free closes ─────────────────────────────────────────
    for key in sorted(saw_accrued):
        inv, loc, ls = key
        qty   = qty_by_key.get(key, 0.0)
        l_bal = accr_local[key]
        b_bal = accr_book[key]
        label = f"{inv} @ {loc} ({ls})"

        if abs(qty) <= 1e-9:
            # Position fully closed -- accrued must be ~zero.
            if abs(l_bal) <= RESIDUAL_TOLERANCE and \
               abs(b_bal) <= RESIDUAL_TOLERANCE:
                result.ok(f"{label} -- closed position, accrued "
                          f"residual {l_bal:.2f} within tolerance",
                          investment=inv)
            else:
                result.fail(
                    f"{label} -- CLOSED position with surviving "
                    f"accrued residual: local={l_bal:.2f} "
                    f"book={b_bal:.2f}. Convention mismatch between "
                    f"code paths, mis-executed recognition policy, "
                    f"or disturbed processing order.",
                    investment=inv)
        else:
            # Position open -- accrued legitimately outstanding.
            result.ok(f"{label} -- open position (qty={qty:,.0f}), "
                      f"accrued balance {l_bal:.2f} carried",
                      investment=inv)

    # ── CHECK 2: vocabulary on accrued accounts ───────────────────────────────
    if bad_txn:
        for period_name, key, txn, fa in bad_txn:
            inv, loc, ls = key
            result.fail(
                f"{period_name} -- {fa} touched by undeclared "
                f"transaction {txn!r} ({inv} @ {loc} ({ls})). Every "
                f"accrued-account JE must carry a declared accrual "
                f"or relief transaction name.",
                period=period_name, investment=inv)
    else:
        result.ok(f"Accrued-account vocabulary clean "
                  f"({len(ACCRUED_TOUCH_ALLOWED)} declared names)")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# PILLAR 8 — ACCRUAL POLICY EXECUTION
# ══════════════════════════════════════════════════════════════════════════════
# Validates that the journal's accrual postings exhibit the DECLARED
# recognition policy's structural signature (Tier A) and amount
# discipline (Tier B). DOMAIN_MODEL Ch. 3/8: "posted accrual equals the
# RESOLVED declared convention."
#
# Would have caught live: stale-config execution (declared
# single_day_factor, executed multiday_preceding) -- the vocabulary/
# policy cross-check fails on the first entry.
#
# Tier A (cheap, structural -- always runs):
#   A1. Vocabulary matches the declared policy per posting date
#       (effective-dated resolution).
#   A2. Date placement: SingleDayFactor entries must be dated ON
#       non-business days; own-day BondAccrual entries on business
#       days; MultiDayPreceding entries on a business day that
#       PRECEDES a gap; MultiDayFollowing on one that FOLLOWS a gap.
#
# Tier B (taxing, amount -- deep=True):
#   B1. Self-referential daily amount: own-day entries establish the
#       daily figure per (investment, location, ls); every gap entry
#       must be that figure x the calendar gap length. No instrument-
#       rate lookup required. NOTE: assumes a stable rate within the
#       examined span; floater resets need per-window grouping when
#       they arrive.
#
# Uses the engine's own calendar (US_HOLIDAYS / _is_holiday_or_weekend)
# rather than importing business_days -- keeps the engine import-clean.
# Resolves the declared policy via global_domain.get_accrual_posting_policy
# (function-level import; skips gracefully if unavailable).

def pillar_accrual_policy(jes_by_period, portfolio: str,
                          deep: bool = True) -> ProofResult:
    """
    Tier A: structural signature of the declared policy.
    Tier B (deep=True): gap amounts are exact multiples of the
    self-established daily amount.
    """
    result = ProofResult("accrual_policy")

    try:
        from global_domain import get_accrual_posting_policy
    except ImportError as e:
        result.skip(f"Policy resolver unavailable "
                    f"(global_domain import failed: {e})")
        return result

    # Collect accrual JEs (one leg per posting: the A/L leg).
    rows = []
    for period_name, jes in sorted(jes_by_period.items()):
        for je in jes:
            txn = str(_je_val(je, "transaction") or "")
            if txn not in ACCRUAL_TXN_VOCABULARY:
                continue
            fa = str(_je_val(je, "financial_account") or "")
            if fa not in ACCRUED_ACCOUNTS:
                continue
            d = _je_date_obj(je, "tradedate")
            if d is None:
                result.fail(f"{period_name} -- accrual JE with "
                            f"unparseable tradedate "
                            f"({_je_val(je, 'investment')})",
                            period=period_name)
                continue
            rows.append({
                "period":     period_name,
                "investment": str(_je_val(je, "investment") or ""),
                "loc":        str(_je_val(je, "location") or ""),
                "ls":         str(_je_val(je, "ls") or ""),
                "date":       d,
                "txn":        txn,
                "local":      _safe_float(_je_val(je, "local")) or 0.0,
            })

    if not rows:
        result.skip("No accrual postings to examine")
        return result

    # ── TIER A — structural signature ─────────────────────────────────────────
    a_fail_count = 0
    for r in rows:
        d = r["date"]
        policy = get_accrual_posting_policy(portfolio, d)
        tag = f"{r['investment']} {d} {r['txn']}"
        nonbiz = _is_holiday_or_weekend(d)

        # A1 -- vocabulary vs declared policy
        if r["txn"] not in POLICY_VOCAB.get(policy, set()):
            result.fail(
                f"{tag} -- transaction belongs to a DIFFERENT election "
                f"than the declared policy '{policy}'. "
                f"Declared-vs-executed divergence.",
                period=r["period"], investment=r["investment"])
            a_fail_count += 1
            continue

        # A2 -- date placement per transaction type
        if r["txn"] == "BondAccrual" and nonbiz:
            result.fail(f"{tag} -- own-day accrual dated on a "
                        f"non-business day.",
                        period=r["period"], investment=r["investment"])
            a_fail_count += 1
        elif r["txn"] == "SingleDayFactor" and not nonbiz:
            result.fail(f"{tag} -- gap-day entry dated on a "
                        f"business day.",
                        period=r["period"], investment=r["investment"])
            a_fail_count += 1
        elif r["txn"] == "MultiDayPreceding":
            if nonbiz:
                result.fail(f"{tag} -- dated on a non-business day.",
                            period=r["period"],
                            investment=r["investment"])
                a_fail_count += 1
            elif not _is_holiday_or_weekend(d + timedelta(days=1)):
                result.fail(f"{tag} -- no gap follows this date; "
                            f"anticipation entry has nothing to "
                            f"anticipate.",
                            period=r["period"],
                            investment=r["investment"])
                a_fail_count += 1
        elif r["txn"] == "MultiDayFollowing":
            if nonbiz:
                result.fail(f"{tag} -- dated on a non-business day.",
                            period=r["period"],
                            investment=r["investment"])
                a_fail_count += 1
            elif not _is_holiday_or_weekend(d - timedelta(days=1)):
                result.fail(f"{tag} -- no gap precedes this date; "
                            f"catch-up entry has nothing to catch up.",
                            period=r["period"],
                            investment=r["investment"])
                a_fail_count += 1

    if a_fail_count == 0:
        result.ok(f"Tier A -- {len(rows)} accrual postings exhibit "
                  f"the declared policy's structural signature")

    # ── TIER B — amount discipline (deep) ─────────────────────────────────────
    if deep:
        by_key = defaultdict(list)
        for r in rows:
            by_key[(r["investment"], r["loc"], r["ls"])].append(r)

        for key, krows in sorted(by_key.items()):
            inv, loc, ls = key
            dailies = [abs(r["local"]) for r in krows
                       if r["txn"] in ("BondAccrual", "SingleDayFactor")
                       and abs(r["local"]) > 0]
            if not dailies:
                result.skip(f"{inv} @ {loc} ({ls}) -- no own-day "
                            f"entries to establish daily amount",
                            investment=inv)
                continue
            daily = sorted(dailies)[len(dailies) // 2]   # median

            key_ok = True
            for r in krows:
                if r["txn"] not in ("MultiDayPreceding",
                                    "MultiDayFollowing"):
                    continue
                d = r["date"]
                n = 0
                if r["txn"] == "MultiDayPreceding":
                    probe = d + timedelta(days=1)
                    while _is_holiday_or_weekend(probe):
                        n += 1
                        probe += timedelta(days=1)
                else:
                    probe = d - timedelta(days=1)
                    while _is_holiday_or_weekend(probe):
                        n += 1
                        probe -= timedelta(days=1)

                expected = daily * n
                if abs(abs(r["local"]) - expected) > MULTIPLE_TOLERANCE:
                    result.fail(
                        f"{inv} {d} {r['txn']} -- amount "
                        f"{abs(r['local']):.2f} != {n} gap day(s) x "
                        f"daily {daily:.2f} = {expected:.2f}",
                        period=r["period"], investment=inv)
                    key_ok = False
            if key_ok:
                result.ok(f"{inv} @ {loc} ({ls}) -- gap amounts are "
                          f"exact multiples of daily {daily:.2f}",
                          investment=inv)

    return result

# ══════════════════════════════════════════════════════════════════════════════
# PILLAR 9 — ORDERING PROVENANCE
# ══════════════════════════════════════════════════════════════════════════════
# Every period's books carry the fingerprint of the precedence
# registry that built them. This pillar reads the stamps:
#   1. Unstamped files (built before provenance existed) -> WARN.
#   2. Stamped file vs CURRENT registry: mismatch is a declared
#      restatement boundary -> WARN with both identities named.
#   3. MIXED fingerprints across the examined files -> FAIL: the
#      books were built under different orderings and are
#      commingled. The one forbidden state.

def pillar_ordering_provenance(period_meta,
                               current_version=None,
                               current_fingerprint=None) -> ProofResult:
    result = ProofResult("ordering_provenance")
    if not period_meta:
        result.skip("No journal files to examine")
        return result

    fps = {}
    for fname, m in sorted(period_meta.items()):
        fp    = m.get("precedence_fingerprint")
        v     = m.get("precedence_version") or "?"
        pname = m.get("period_name", "")

        if fp is None:
            result.warn(f"{fname} -- unstamped (built before ordering "
                        f"provenance existed); reprocess to stamp.",
                        period=pname)
            continue

        fps.setdefault(fp, []).append(fname)

        if current_fingerprint is None:
            result.ok(f"{fname} -- stamped {v}/{fp}", period=pname)
        elif fp == current_fingerprint:
            result.ok(f"{fname} -- built under current ordering "
                      f"({v}/{fp})", period=pname)
        else:
            result.warn(f"{fname} -- built under {v}/{fp}; current "
                        f"registry is {current_version}/"
                        f"{current_fingerprint}. Reprocessing this "
                        f"period is a RESTATEMENT, not a reproduction.",
                        period=pname)

    if len(fps) > 1:
        detail = "; ".join(f"{fp}: {len(files)} file(s)"
                           for fp, files in sorted(fps.items()))
        result.fail(f"MIXED orderings within one book: {detail}. "
                    f"Periods built under different precedence "
                    f"registries are commingled -- reprocess to a "
                    f"single ordering before relying on cross-period "
                    f"results.")

    if current_fingerprint is None:
        result.skip("Current registry unavailable in proof context -- "
                    "stamped-vs-current comparison skipped")

    return result

# ══════════════════════════════════════════════════════════════════════════════
# CPH INTEGRATION HOOKS (optional)
# ══════════════════════════════════════════════════════════════════════════════

def run_proof_pre_cph(portfolio: str, calendar: str,
                      funds_path: str = None,
                      refdata_path: str = None,
                      block_on_critical: bool = True) -> bool:
    """
    Optional pre-CPH data validation.
    Returns True if safe to proceed, False if critical issues found.
    Set block_on_critical=False to warn but not block.
    """
    fp = funds_path or str(FUNDS_PATH)
    rp = refdata_path or str(REFDATA_PATH)

    im = load_investment_master(portfolio, fp)
    events = load_events(portfolio, fp)
    result = pillar_data(events, im=im)


    critical_count = len(result.criticals)
    print(f"\n>>> PRE-CPH DATA CHECK | {portfolio} | {calendar}")
    print(f"    D-checks: {len(result.passes)} pass | "
          f"{len(result.warnings)} warn | "
          f"{len(result.failures)} fail | "
          f"{critical_count} critical")

    if critical_count > 0:
        print(f"    {'⛔ BLOCKING' if block_on_critical else '⚠ WARNING'}: "
              f"{critical_count} critical data issues found")
        for item in result.criticals[:3]:
            print(f"    → {item.message}")
        if block_on_critical:
            return False

    return True


def run_proof_post_cph(portfolio: str, calendar: str,
                       period: str = None,
                       funds_path: str = None,
                       refdata_path: str = None) -> ProofResult:
    """
    Optional post-CPH validation.
    Runs marks pillar to verify MV integrity after processing.
    """
    fp = funds_path or str(FUNDS_PATH)
    rp = refdata_path or str(REFDATA_PATH)

    events           = load_events(portfolio, fp)
    im               = load_investment_master(portfolio, fp)
    price_index      = load_price_index(rp)
    fx_index         = load_fx_index(rp)
    jes_by_period, _ = load_jes_from_journals(portfolio, calendar, fp, period)
    calendar_records = load_calendar_records(portfolio, calendar, fp)

    if period:
        calendar_records = [r for r in calendar_records
                           if r.get("period_name") == period]
        jes_by_period = _filter_periods(jes_by_period, period=period)

    result = pillar_marks(events, im, calendar_records,
                          jes_by_period, price_index, fx_index)

    fail_count = len(result.failures)
    print(f"\n>>> POST-CPH MARKS CHECK | {portfolio} | {calendar} | {period or 'ALL'}")
    print(f"    {len(result.passes)} proved | {len(result.warnings)} warn | "
          f"{fail_count} failed")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# PRINT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _print_pillar(result: ProofResult, verbose: bool = False):
    label = result.pillar.upper()
    status = f"{GREEN}ALL CLEAR{RESET}" if result.all_clear else f"{RED}ISSUES FOUND{RESET}"
    print(f"\n{BOLD}{BLUE}── PILLAR: {label}{RESET}  {status}")
    print(f"   {GREEN}✓ {len(result.passes)}{RESET}  "
          f"{YELLOW}⚠ {len(result.warnings)}{RESET}  "
          f"{RED}✗ {len(result.failures)}{RESET}  "
          f"{DIM}skip {len(result.skipped)}{RESET}")

    if result.failures:
        print(f"\n   {RED}FAILURES:{RESET}")
        for item in result.failures:
            sev = f"[{item.severity}] " if item.severity == "CRITICAL" else ""
            print(f"   {RED}✗ FAIL{RESET}  {sev}{item.message}")

    if result.warnings:
        print(f"\n   {YELLOW}WARNINGS:{RESET}")
        for item in result.warnings:
            print(f"   {YELLOW}⚠ WARN{RESET}  {item.message}")

    if verbose and result.passes:
        print(f"\n   {GREEN}PASSES:{RESET}")
        for item in result.passes:
            print(f"   {GREEN}✓ PASS{RESET}  {item.message}")

    if verbose and result.skipped:
        for item in result.skipped:
            print(f"   {DIM}  SKIP  {item.message}{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_proof(portfolio: str, calendar: str,
              period: str = None,
              period_from: str = None,
              period_to: str = None,
              tranid_filter: int = None,
              investment_filter: str = None,
              pillar_filter: str = None,
              verbose: bool = False,
              funds_path: str = None,
              refdata_path: str = None) -> list:

    fp = funds_path or str(FUNDS_PATH)
    rp = refdata_path or str(REFDATA_PATH)

    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"{BOLD}  VAI PROOF ENGINE — Visibility{RESET}")
    print(f"  Portfolio  : {portfolio}")
    print(f"  Calendar   : {calendar}")
    print(f"  Period     : {period or (f'{period_from} → {period_to}' if period_from else 'ALL')}")
    if investment_filter: print(f"  Investment : {investment_filter}")
    if pillar_filter:     print(f"  Pillar     : {pillar_filter}")
    print(f"{'═'*65}{RESET}\n")

    # ── LOAD ──────────────────────────────────────────────────────────────────
    print("Loading data...")
    events           = load_events(portfolio, fp)
    im               = load_investment_master(portfolio, fp)
    price_index      = load_price_index(rp)
    fx_index         = load_fx_index(rp)
    jes_by_period    = load_jes_from_journals(portfolio, calendar, fp, period)
    calendar_records = load_calendar_records(portfolio, calendar, fp)

    # Filter periods
    jes_by_period, period_meta = load_jes_from_journals(portfolio, calendar, fp, period)

    # Current registry identity, for stamped-vs-current comparison.
    # If the scheduler can't be constructed in this context, Pillar 9
    # still runs its internal-consistency checks and says so.
    try:
        from bookkeeping import precedence_fingerprint as _pfp
        from bookkeeping import EventScheduler as _ES
        _sched = _ES()
        current_version = _sched.precedence_version
        current_fingerprint = _pfp(_sched.event_type_precedence)
    except Exception as _e:
        print(f"  (current registry unavailable to proof engine: {_e})")
        current_version = None
        current_fingerprint = None
    if period:
        calendar_records = [r for r in calendar_records
                           if r.get("period_name") == period]
    elif period_from or period_to:
        calendar_records = [r for r in calendar_records
                           if (not period_from or r.get("period_name","") >= period_from)
                           and (not period_to or r.get("period_name","") <= period_to)]

    # Apply filters
    if investment_filter:
        inv_upper = investment_filter.upper()
        events = [e for e in events
                 if e.get("investment","").upper() == inv_upper]
    if tranid_filter:
        events = [e for e in events
                 if int(_safe_float(e.get("tranid")) or 0) == tranid_filter]

    print(f"  Events: {len(events)}  |  "
          f"Periods: {len(jes_by_period)}  |  "
          f"Prices: {len(price_index)}  |  "
          f"FX: {len(fx_index)}")

    # ── RUN PILLARS ───────────────────────────────────────────────────────────
    results = []
    run_all = pillar_filter is None

    pillar_map = {
        "availability":      lambda: pillar_availability(events, im, calendar_records, price_index, fx_index),
        "balance":           lambda: pillar_balance(jes_by_period),
        "settle_fx":         lambda: pillar_settle_fx(events, jes_by_period, fx_index),
        "marks":             lambda: pillar_marks(events, im, calendar_records, jes_by_period, price_index, fx_index),
        "chart_of_accounts": lambda: pillar_chart_of_accounts(jes_by_period),
        "data":              lambda: pillar_data(events, jes_by_period, im),
        "accrual_residual":  lambda: pillar_accrual_residual(jes_by_period),
        "accrual_policy":    lambda: pillar_accrual_policy(jes_by_period, portfolio, deep=True),
        "ordering_provenance": lambda: pillar_ordering_provenance(period_meta, current_version, current_fingerprint),
    }

    for name, fn in pillar_map.items():
        if run_all or pillar_filter == name:
            print(f"\n{CYAN}Running {name}...{RESET}")
            r = fn()
            results.append(r)
            if verbose:
                _print_pillar(r, verbose=True)

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    _print_summary_grid(results)
    return results

# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="VAI Proof Engine — Visibility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pillars:
  availability      prices and FX rates exist for all required dates
  balance           debits = credits every period
  settle_fx         trade/settle FX G/L uses correct rate
  marks             period end MV = qty x price x pf x fx_rate
  chart_of_accounts every account posted exists in COA
  data              event file integrity (kdbegin, holidays, qty, price, dupes)
  accrual_residual  closed positions carry no accrued residual; accrued
                    accounts touched only by declared transaction names
  accrual_policy    journal postings exhibit the fund's declared accrual
                    election (vocabulary, date placement, gap multiples)
  ordering_provenance every period's books match the precedence registry
                    that built them; mixed orderings are forbidden

Examples:
  python proof_engine.py Portfolio1 Monthly
  python proof_engine.py Portfolio1 Monthly 2024-06
  python proof_engine.py Portfolio1 Monthly --period-from 2024-01 --period-to 2024-06
  python proof_engine.py Portfolio1 Monthly --pillar marks --verbose
  python proof_engine.py Portfolio1 Monthly --pillar accrual_policy --verbose
  python proof_engine.py Portfolio1 Monthly --investment AAPL --verbose
        """
    )
    parser.add_argument("portfolio")
    parser.add_argument("calendar")
    parser.add_argument("period",        nargs="?")
    parser.add_argument("--period-from", type=str)
    parser.add_argument("--period-to",   type=str)
    parser.add_argument("--tranid",      type=int)
    parser.add_argument("--investment",  type=str)
    parser.add_argument("--pillar", type=str,
                        choices=["availability", "balance", "settle_fx",
                                 "marks", "chart_of_accounts", "data",
                                 "accrual_residual", "accrual_policy",
                                 "ordering_provenance"])
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--raw", action="store_true",
                        help="skip the readable report, show only the engine's native output")
    parser.add_argument("--funds", default=None)
    parser.add_argument("--refdata",     default=None)

    args = parser.parse_args()

    results = run_proof(
        portfolio=args.portfolio,
        calendar=args.calendar,
        period=args.period,
        period_from=args.period_from,
        period_to=args.period_to,
        tranid_filter=args.tranid,
        investment_filter=args.investment,
        pillar_filter=args.pillar,
        verbose=args.verbose,
        funds_path=args.funds,
        refdata_path=args.refdata,
    )

    # ── Readable report (additive; --raw skips it) ──
    if not args.raw:
        try:
            from proof_report import render_report

            render_report(results)
        except ImportError:
            print("  (proof_report.py not found — skipping readable report)")

    has_critical = any(r.has_critical for r in results)
    has_failures = any(not r.all_clear for r in results)
    sys.exit(2 if has_critical else 1 if has_failures else 0)