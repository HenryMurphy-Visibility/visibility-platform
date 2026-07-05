# -*- coding: utf-8 -*-
"""
bond_accrual.py — Visibility Bond Accrual Calculator
Calculates accrued interest for bond purchase/sale events.
Coupon rate stored as real percentage (5 = 5%, not 0.05).
Accrual based on settlement date — standard market convention.

Henry J. Murphy — Chest Financial Systems
"""

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


# ============================================================
# COUPON DATE GENERATION
# Uses exact month arithmetic — not timedelta approximation
# ============================================================

def generate_coupon_dates(issue_date, first_coupon_date, maturity_date, payment_frequency):
    """
    Generate all coupon dates from first coupon to maturity.
    Uses exact month arithmetic for accuracy.
    """
    if isinstance(issue_date,        str): issue_date        = datetime.strptime(issue_date,        "%m/%d/%Y")
    if isinstance(first_coupon_date, str): first_coupon_date = datetime.strptime(first_coupon_date, "%m/%d/%Y")
    if isinstance(maturity_date,     str): maturity_date     = datetime.strptime(maturity_date,     "%m/%d/%Y")

    freq_months = {
        "ANNUAL":      12,
        "SEMI_ANNUAL":  6,
        "QUARTERLY":    3,
        "MONTHLY":      1,
    }

    months = freq_months.get(payment_frequency.upper())
    if months is None:
        raise ValueError(f"Unsupported payment frequency: {payment_frequency}")

    dates = []
    current = first_coupon_date
    while current <= maturity_date:
        dates.append(current)
        current = current + relativedelta(months=months)

    return dates


# ============================================================
# ACCRUED INTEREST CALCULATION
# Settlement date based — standard market convention
# Coupon rate as real percentage (5 = 5%)
# ============================================================

def calculate_accrued_interest(
    issue_date,
    first_coupon_date,
    maturity_date,
    settlement_date,
    coupon_rate,          # Real percentage — 5 means 5%
    payment_frequency,
    day_count_convention,
    face_value=100,
    semi_split="A",
):
    """
    Calculate accrued interest for a bond transaction.

    Parameters
    ----------
    issue_date           : str or datetime — bond issue date
    first_coupon_date    : str or datetime — first coupon payment date
    maturity_date        : str or datetime — bond maturity date
    settlement_date      : str or datetime — SETTLEMENT date (not trade date)
    coupon_rate          : float — REAL percentage e.g. 5 for 5%
    payment_frequency    : str — ANNUAL, SEMI_ANNUAL, QUARTERLY, MONTHLY
    day_count_convention : str — see supported list below
    face_value           : float — face value per unit (default 100)
    semi_split           : str — A (actual) or C (calendar)

    Supported day count conventions:
        30/360 Bond Basis
        30/360 ISDA
        30E/360
        actual/360
        actual/365
        actual/actual ISDA
        actual/actual ICMA

    Returns
    -------
    dict with:
        accrued_per_100      : accrued interest per 100 face value
        accrued_total        : accrued interest on full face value
        daily_per_100        : daily accrual per 100 face value
        days_of_accrual      : days since last coupon
        days_in_period       : total days in coupon period
        last_coupon_date     : prior coupon date
        next_coupon_date     : next coupon date
        semi_annual_coupon   : coupon payment per period per 100 face
    """
    # ── PARSE DATES ───────────────────────────────────────────
    def _parse(d):
        if isinstance(d, datetime): return d
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y:%H:%M:%S"):
            try: return datetime.strptime(d.split(":")[0] if ":" in d and len(d) > 10 else d, fmt.split(":")[0] if ":" in fmt else fmt)
            except: pass
        raise ValueError(f"Cannot parse date: {d}")

    issue_date        = _parse(issue_date)
    first_coupon_date = _parse(first_coupon_date)
    maturity_date     = _parse(maturity_date)
    settlement_date   = _parse(settlement_date)

    # ── COUPON RATE AS DECIMAL ────────────────────────────────
    rate = float(coupon_rate) / 100.0  # 5 → 0.05

    # ── FREQUENCY ─────────────────────────────────────────────
    freq_map = {
        "ANNUAL": 1, "SEMI_ANNUAL": 2, "QUARTERLY": 4, "MONTHLY": 12
    }
    freq = freq_map.get(payment_frequency.upper())
    if freq is None:
        raise ValueError(f"Unsupported frequency: {payment_frequency}")

    periodic_rate = rate / freq  # coupon payment per period per unit of face

    # ── COUPON DATES ──────────────────────────────────────────
    coupon_dates = generate_coupon_dates(
        issue_date, first_coupon_date, maturity_date, payment_frequency
    )

    # ── FIND LAST AND NEXT COUPON RELATIVE TO SETTLEMENT ─────
    past   = [d for d in coupon_dates if d <= settlement_date]
    future = [d for d in coupon_dates if d >  settlement_date]

    last_coupon = max(past)   if past   else issue_date
    next_coupon = min(future) if future else maturity_date

    # ── On coupon date — accrued = 0 ─────────────────────────
    if settlement_date in coupon_dates:
        return {
            "accrued_per_100":    0.0,
            "accrued_total":      0.0,
            "daily_per_100":      0.0,
            "days_of_accrual":    0,
            "days_in_period":     (next_coupon - last_coupon).days,
            "last_coupon_date":   last_coupon,
            "next_coupon_date":   next_coupon,
            "semi_annual_coupon": periodic_rate * face_value,
            "note":               "Settlement on coupon date — accrued = 0",
        }

    # ── DAY COUNT ─────────────────────────────────────────────
    dcc = day_count_convention.upper().replace(" ", "").replace("/", "").replace("-", "")

    def days_30_360(d1, d2):
        """Standard 30/360."""
        y1, m1, day1 = d1.year, d1.month, min(d1.day, 30)
        y2, m2, day2 = d2.year, d2.month, min(d2.day, 30)
        return 360*(y2-y1) + 30*(m2-m1) + (day2-day1)

    def days_30e_360(d1, d2):
        """30E/360 — European convention."""
        y1, m1, day1 = d1.year, d1.month, min(d1.day, 30)
        y2, m2, day2 = d2.year, d2.month, min(d2.day, 30)
        return 360*(y2-y1) + 30*(m2-m1) + (day2-day1)

    def days_30_360_isda(d1, d2):
        """30/360 ISDA."""
        day1 = 30 if d1.day == 31 else d1.day
        day2 = 30 if (d2.day == 31 and d1.day in [30, 31]) else d2.day
        return 360*(d2.year-d1.year) + 30*(d2.month-d1.month) + (day2-day1)

    if dcc in ("30360BONDBASIS", "30360US", "30360"):
        days_accrual  = days_30_360(last_coupon, settlement_date)
        days_period   = days_30_360(last_coupon, next_coupon)

    elif dcc == "30E360":
        days_accrual  = days_30e_360(last_coupon, settlement_date)
        days_period   = days_30e_360(last_coupon, next_coupon)

    elif dcc == "30360ISDA":
        days_accrual  = days_30_360_isda(last_coupon, settlement_date)
        days_period   = days_30_360_isda(last_coupon, next_coupon)

    elif dcc == "ACTUAL360":
        days_accrual  = (settlement_date - last_coupon).days
        days_period   = 360 // freq  # conventional period

    elif dcc == "ACTUAL365":
        days_accrual  = (settlement_date - last_coupon).days
        days_period   = 365 // freq

    elif dcc in ("ACTUALACTUAL", "ACTUALACTUALISDA"):
        days_accrual  = (settlement_date - last_coupon).days
        days_period   = (next_coupon - last_coupon).days

    elif dcc == "ACTUALACTUAICMA":
        days_accrual  = (settlement_date - last_coupon).days
        days_period   = (next_coupon - last_coupon).days

    else:
        raise ValueError(f"Unsupported day count convention: {day_count_convention}")

    # ── CALCULATE ACCRUED ─────────────────────────────────────
    if days_period == 0:
        raise ValueError("days_in_period is zero — check bond dates")

    accrued_per_100 = periodic_rate * face_value * days_accrual / days_period
    daily_per_100   = periodic_rate * face_value / days_period
    accrued_total   = accrued_per_100  # per 100 face — caller multiplies by quantity/100

    return {
        "accrued_per_100":    round(accrued_per_100, 6),
        "accrued_total":      round(accrued_total,   6),
        "daily_per_100":      round(daily_per_100,   6),
        "days_of_accrual":    days_accrual,
        "days_in_period":     days_period,
        "last_coupon_date":   last_coupon,
        "next_coupon_date":   next_coupon,
        "semi_annual_coupon": round(periodic_rate * face_value, 6),
        "coupon_rate_pct":    float(coupon_rate),
        "coupon_rate_dec":    rate,
        "settlement_date":    settlement_date,
        "day_count":          day_count_convention,
        "frequency":          payment_frequency,
    }


# ============================================================
# QUICK TEST
# ============================================================

if __name__ == "__main__":
    # BND000 — 5% semi-annual 30E/360
    # Bought settling 2026-01-05
    # Last coupon: 2026-01-15 (future) → last coupon was 2025-07-15
    result = calculate_accrued_interest(
        issue_date           = "01/15/2015",
        first_coupon_date    = "07/15/2015",
        maturity_date        = "01/15/2028",
        settlement_date      = "01/05/2026",
        coupon_rate          = 5,             # 5% — real percentage
        payment_frequency    = "SEMI_ANNUAL",
        day_count_convention = "30E/360",
        face_value           = 100,
        semi_split           = "A",
    )

    print("\nBND000 — Accrual on settlement 2026-01-05")
    print(f"Last coupon date  : {result['last_coupon_date'].strftime('%Y-%m-%d')}")
    print(f"Next coupon date  : {result['next_coupon_date'].strftime('%Y-%m-%d')}")
    print(f"Days of accrual   : {result['days_of_accrual']}")
    print(f"Days in period    : {result['days_in_period']}")
    print(f"Semi-annual coupon: {result['semi_annual_coupon']} per 100 face")
    print(f"Daily per 100     : {result['daily_per_100']:.6f}")
    print(f"Accrued per 100   : {result['accrued_per_100']:.6f}")
    print()
    print(f"For $1,000,000 face:")
    face = 1_000_000
    accrued = result['accrued_per_100'] * face / 100
    daily   = result['daily_per_100']   * face / 100
    print(f"  Daily accrual   : ${daily:,.2f}")
    print(f"  Accrued on buy  : ${accrued:,.2f}")
    print(f"  Dirty price     : cost + ${accrued:,.2f}")