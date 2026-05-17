# ============================================================
# calendar_generator.py
# Visibility — Calendar File Generator
#
# Generates calendar .txt files for a portfolio from
# inception_date to today. One JSON record per line.
#
# Supports: Monthly, Daily, Quarterly, Yearly
#
# Called by ops_routes.py when creating a portfolio.
# Can also be run standalone to regenerate calendars.
#
# Henry J. Murphy — Chest Financial Systems
# ============================================================

import json
import os
from pathlib import Path
from datetime import datetime, date
from calendar import monthrange
from typing import List

from v_config import FUNDS_PATH

CAL_DATE_FMT = "%Y-%m-%d:%H:%M:%S"


def _fmt(dt: datetime) -> str:
    return dt.strftime(CAL_DATE_FMT)


def _dt(d: date, hour=0, minute=0, second=0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, second)


# ============================================================
# PERIOD BOUNDARY CALCULATORS
# ============================================================

def _monthly_periods(inception: date, through: date) -> list:
    """
    Generate monthly period boundaries from inception through today.
    First period starts on actual inception date (handles mid-month start).
    Subsequent periods start on first of month.
    """
    periods = []
    year, month = inception.year, inception.month
    first = True

    while date(year, month, 1) <= through:
        # First period starts on inception date, rest start on first of month
        period_start  = inception if first else date(year, month, 1)
        last_day      = monthrange(year, month)[1]
        period_cutoff = date(year, month, last_day)
        period_name   = f"{year}-{month:02d}"

        periods.append((period_name, period_start, period_cutoff))
        first = False

        month += 1
        if month > 12:
            month = 1
            year += 1

    return periods


def _quarterly_periods(inception: date, through: date) -> list:
    """Generate quarterly period boundaries."""
    periods = []
    year    = inception.year
    quarter = (inception.month - 1) // 3 + 1

    quarter_ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}

    first = True
    while True:
        q_start_month = (quarter - 1) * 3 + 1
        q_end_month, q_end_day = quarter_ends[quarter]

        period_start  = inception if first else date(year, q_start_month, 1)
        period_cutoff = date(year, q_end_month, q_end_day)
        period_name   = f"{year}-Q{quarter}"

        if date(year, q_start_month, 1) > through:
            break

        periods.append((period_name, period_start, period_cutoff))
        first = False

        quarter += 1
        if quarter > 4:
            quarter = 1
            year   += 1

    return periods


def _yearly_periods(inception: date, through: date) -> list:
    """Generate yearly period boundaries."""
    periods = []
    year    = inception.year

    first = True
    while year <= through.year:
        period_start  = inception if first else date(year, 1, 1)
        period_cutoff = date(year, 12, 31)
        period_name   = str(year)

        periods.append((period_name, period_start, period_cutoff))
        first = False
        year += 1

    return periods


def _daily_periods(inception: date, through: date) -> list:
    """Generate daily period boundaries."""
    from datetime import timedelta
    periods = []
    current = inception

    while current <= through:
        period_name = current.strftime("%Y-%m-%d")
        periods.append((period_name, current, current))
        current += timedelta(days=1)

    return periods


# ============================================================
# CALENDAR RECORD BUILDER
# ============================================================

def _build_records(periods: list, now: datetime) -> list:
    """
    Build calendar records from period boundaries.

    Rules:
    - First period: prior_* fields all point to inception (no prior)
    - All periods start as Pending with current_period_knowledge = now
    - prior_period fields derived from previous period
    """
    records = []

    for i, (period_name, period_start, period_cutoff) in enumerate(periods):

        if i == 0:
            # First period — no prior
            prior_period_start    = period_start
            prior_period_cutoff   = period_start
            prior_period_knowledge = period_start
        else:
            prev_name, prev_start, prev_cutoff = periods[i - 1]
            prior_period_start    = prev_start
            prior_period_cutoff   = prev_cutoff
            prior_period_knowledge = prev_cutoff

        record = {
            "period_name":              period_name,
            "period_status":            "Pending",
            "current_period_start":     _fmt(_dt(period_start,  0,  0,  0)),
            "current_period_cutoff":    _fmt(_dt(period_cutoff, 23, 59, 59)),
            "current_period_knowledge": _fmt(now),
            "prior_period_start":       _fmt(_dt(prior_period_start,     0,  0,  0)),
            "prior_period_cutoff":      _fmt(_dt(prior_period_cutoff,    23, 59, 59)
                                             if prior_period_cutoff != period_start
                                             else _dt(prior_period_cutoff, 0, 0, 0)),
            "prior_period_knowledge":   _fmt(_dt(prior_period_knowledge, 23, 59, 59)
                                             if prior_period_knowledge != period_start
                                             else _dt(prior_period_knowledge, 0, 0, 0)),
        }

        records.append(record)

    return records


# ============================================================
# MAIN GENERATOR
# ============================================================

def generate_calendar(
    portfolio:      str,
    calendar:       str,
    inception_date: str,
    through_date:   str = None,
) -> dict:
    """
    Generate a calendar file for a portfolio.

    Parameters
    ----------
    portfolio      : Portfolio identifier e.g. "Portfolio2"
    calendar       : "Monthly" | "Daily" | "Quarterly" | "Yearly"
    inception_date : YYYY-MM-DD
    through_date   : YYYY-MM-DD (defaults to today)

    Returns
    -------
    dict with keys: calendar, periods_created, path
    """

    # Parse dates
    inception = datetime.strptime(inception_date, "%Y-%m-%d").date()
    through   = (
        datetime.strptime(through_date, "%Y-%m-%d").date()
        if through_date
        else date.today()
    )
    now = datetime.now()

    if inception > through:
        through = inception

    # Generate period boundaries
    generators = {
        "Monthly":   _monthly_periods,
        "Daily":     _daily_periods,
        "Quarterly": _quarterly_periods,
        "Yearly":    _yearly_periods,
    }

    if calendar not in generators:
        raise ValueError(
            f"Unknown calendar: '{calendar}'. "
            f"Valid: {list(generators.keys())}"
        )

    periods = generators[calendar](inception, through)

    if not periods:
        raise ValueError(
            f"No periods generated for {calendar} "
            f"from {inception_date} through {through}"
        )

    # Build records
    records = _build_records(periods, now)

    # Create calendar directory
    cal_dir = (
        Path(FUNDS_PATH) / portfolio / "Calendars" / calendar
    )
    cal_dir.mkdir(parents=True, exist_ok=True)

    # Create Snapshots directory
    (cal_dir / "Snapshots").mkdir(exist_ok=True)
    (cal_dir / "Journals").mkdir(exist_ok=True)

    # Write calendar file
    cal_path = cal_dir / f"{calendar}.txt"
    with open(cal_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print(f">>> CALENDAR GENERATED | {portfolio} | {calendar} | "
          f"{len(records)} periods | {inception_date} → {through}")

    return {
        "calendar":        calendar,
        "periods_created": len(records),
        "inception_date":  inception_date,
        "through_date":    str(through),
        "path":            str(cal_path),
    }


def generate_calendars(
    portfolio:      str,
    calendars:      List[str],
    inception_date: str,
    through_date:   str = None,
) -> list:
    """
    Generate multiple calendars for a portfolio.
    Called at portfolio creation time.
    """
    results = []
    for calendar in calendars:
        result = generate_calendar(
            portfolio=portfolio,
            calendar=calendar,
            inception_date=inception_date,
            through_date=through_date,
        )
        results.append(result)
    return results


# ============================================================
# CALENDAR PRESETS
# ============================================================

CALENDAR_PRESETS = {
    "Institutional": ["Monthly"],
    "Hedge Fund":    ["Daily", "Monthly"],
    "Full":          ["Daily", "Monthly", "Quarterly", "Yearly"],
}


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python calendar_generator.py "
              "<portfolio> <calendar> <inception_date> [through_date]")
        print("       calendar: Monthly | Daily | Quarterly | Yearly | ALL")
        sys.exit(1)

    portfolio      = sys.argv[1]
    calendar_arg   = sys.argv[2]
    inception_date = sys.argv[3]
    through_date   = sys.argv[4] if len(sys.argv) > 4 else None

    if calendar_arg == "ALL":
        results = generate_calendars(
            portfolio, ["Daily","Monthly","Quarterly","Yearly"],
            inception_date, through_date
        )
    else:
        results = [generate_calendar(
            portfolio, calendar_arg, inception_date, through_date
        )]

    for r in results:
        print(f"  {r['calendar']}: {r['periods_created']} periods → {r['path']}")