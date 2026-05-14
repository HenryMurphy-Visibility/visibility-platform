# business_days.py
from datetime import date, datetime, timedelta

# ------------------------------------------------------------
# U.S. MARKET HOLIDAYS (NYSE/NASDAQ) — 2019 THROUGH 2027
# Includes Good Friday
# ------------------------------------------------------------

US_HOLIDAYS = {
    # ------------------ 2019 ------------------
    date(2019, 1, 1),    # New Year's Day
    date(2019, 1, 21),   # MLK Day
    date(2019, 2, 18),   # Presidents' Day
    date(2019, 4, 19),   # Good Friday
    date(2019, 5, 27),   # Memorial Day
    date(2019, 7, 4),    # Independence Day
    date(2019, 9, 2),    # Labor Day
    date(2019, 11, 28),  # Thanksgiving
    date(2019, 12, 25),  # Christmas

    # ------------------ 2020 ------------------
    date(2020, 1, 1),
    date(2020, 1, 20),
    date(2020, 2, 17),
    date(2020, 4, 10),   # Good Friday
    date(2020, 5, 25),
    date(2020, 7, 3),    # Independence Day (Observed)
    date(2020, 9, 7),
    date(2020, 11, 26),
    date(2020, 12, 25),

    # ------------------ 2021 ------------------
    date(2021, 1, 1),
    date(2021, 1, 18),
    date(2021, 2, 15),
    date(2021, 4, 2),    # Good Friday
    date(2021, 5, 31),
    date(2021, 7, 5),    # Independence Day (Observed)
    date(2021, 9, 6),
    date(2021, 11, 25),
    date(2021, 12, 24),  # Christmas (Observed)

    # ------------------ 2022 ------------------
    date(2022, 1, 17),
    date(2022, 2, 21),
    date(2022, 4, 15),   # Good Friday
    date(2022, 5, 30),
    date(2022, 6, 20),   # Juneteenth (Observed)
    date(2022, 7, 4),
    date(2022, 9, 5),
    date(2022, 11, 24),
    date(2022, 12, 26),  # Christmas (Observed)

    # ------------------ 2023 ------------------
    date(2023, 1, 2),    # New Year's (Observed)
    date(2023, 1, 16),
    date(2023, 2, 20),
    date(2023, 4, 7),    # Good Friday
    date(2023, 5, 29),
    date(2023, 6, 19),
    date(2023, 7, 4),
    date(2023, 9, 4),
    date(2023, 11, 23),
    date(2023, 12, 25),

    # ------------------ 2024 ------------------
    date(2024, 1, 1),
    date(2024, 1, 15),
    date(2024, 2, 19),
    date(2024, 3, 29),   # Good Friday
    date(2024, 5, 27),
    date(2024, 6, 19),
    date(2024, 7, 4),
    date(2024, 9, 2),
    date(2024, 11, 28),
    date(2024, 12, 25),

    # ------------------ 2025 ------------------
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 26),
    date(2025, 6, 19),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),

    # ------------------ 2026 ------------------
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),    # Independence Day (Observed)
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),

    # ------------------ 2027 ------------------
    date(2027, 1, 1),
    date(2027, 1, 18),
    date(2027, 2, 15),
    date(2027, 3, 26),   # Good Friday
    date(2027, 5, 31),
    date(2027, 6, 18),   # Juneteenth (Observed)
    date(2027, 7, 5),    # Independence Day (Observed)
    date(2027, 9, 6),
    date(2027, 11, 25),
    date(2027, 12, 24),  # Christmas (Observed)
}


# ------------------------------------------------------------
# Utility Functions
# ------------------------------------------------------------

from datetime import datetime


# ============================================================
# AUTHORITATIVE BUSINESS-DAY GENERATOR
# ============================================================

def generate_business_days(
        start_date=None,
        end_date=None
):
    """
    Generate business days using Visibility rules:
    - Excludes weekends
    - Excludes US_HOLIDAYS
    """
    if start_date is None:
        start_date = date(2000, 1, 1)

    if end_date is None:
        end_date = date(2100, 12, 31)

    d = start_date
    days = []

    while d <= end_date:
        # WEEKEND EXCLUSION BELONGS HERE — NOT IN is_non_business_day
        if d.weekday() < 5 and d not in US_HOLIDAYS:
            days.append(d)
        d += timedelta(days=1)

    return days


# ============================================================
# PRECOMPUTED BUSINESS DAY SET (AUTHORITATIVE)
# ============================================================

BUSINESS_DAYS_SET = set(generate_business_days())


# ============================================================
# NON-BUSINESS DAY TEST (PUBLIC API — DO NOT RENAME)
# ============================================================

def is_non_business_day(d):
    """
    Visibility-authoritative non-business-day test.

    IMPORTANT:
    - Call sites MUST NOT use weekday()
    - All logic funnels through BUSINESS_DAYS_SET
    """
    if isinstance(d, datetime):
        d = d.date()

    return d not in BUSINESS_DAYS_SET


def get_next_business_day(d):
    if isinstance(d, datetime):
        d = d.date()
    nd = d + timedelta(days=1)
    while is_non_business_day(nd):
        nd += timedelta(days=1)
    return datetime.combine(nd, datetime.min.time())


def get_previous_business_day(d):
    if isinstance(d, datetime):
        d = d.date()
    pd = d - timedelta(days=1)
    while is_non_business_day(pd):
        pd -= timedelta(days=1)
    return datetime.combine(pd, datetime.min.time())


def generate_business_days(start, end):
    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()

    cur = start
    results = []
    while cur <= end:
        if not is_non_business_day(cur):
            results.append(datetime.combine(cur, datetime.min.time()))
        cur += timedelta(days=1)
    return results
