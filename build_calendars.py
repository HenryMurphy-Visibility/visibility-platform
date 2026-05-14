# build_calendars.py
import os
import json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


BASE_PATH = "C:/Users/hjmne/PycharmProjects/chest"
DATE_FMT = "%Y-%m-%d:%H:%M:%S"


def fmt(dt):
    return dt.strftime(DATE_FMT)


def write_calendar(portfolio, calendar_name, records):
    cal_dir = (
        f"{BASE_PATH}/funds/{portfolio}/Calendars/{calendar_name}"
    )
    os.makedirs(cal_dir, exist_ok=True)

    out_path = f"{cal_dir}/{calendar_name}.txt"

    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    print(f"✔ Wrote {len(records)} records → {out_path}")


def build_periods(start, end, cadence):
    periods = []

    cur = start
    while cur <= end:
        if cadence == "Daily":
            p_start = cur
            p_end = cur.replace(hour=23, minute=59, second=59)
            name = cur.strftime("%Y-%m-%d")
            cur += timedelta(days=1)

        elif cadence == "Monthly":
            p_start = cur.replace(day=1, hour=0, minute=0, second=0)
            p_end = (p_start + relativedelta(months=1)) - timedelta(seconds=1)
            name = p_start.strftime("%Y-%m")
            cur = p_start + relativedelta(months=1)

        elif cadence == "Quarterly":
            q = (cur.month - 1) // 3 * 3 + 1
            p_start = cur.replace(month=q, day=1, hour=0, minute=0, second=0)
            p_end = (p_start + relativedelta(months=3)) - timedelta(seconds=1)
            name = f"{p_start.year}-Q{((q - 1) // 3) + 1}"
            cur = p_start + relativedelta(months=3)

        periods.append((name, p_start, p_end))

    return periods


def build_calendar(portfolio, cadence, start_date, end_date):
    periods = build_periods(start_date, end_date, cadence)
    records = []

    prev_start = None
    prev_end = None

    for i, (name, p_start, p_end) in enumerate(periods):
        if i == 0:
            prior_start = p_start
            prior_end = p_start
        else:
            prior_start = prev_start
            prior_end = prev_end

        rec = {
            "period_name": name,
            "period_status": "Pending" if p_end >= datetime.now() else "Closed",

            "current_period_start": fmt(p_start),
            "current_period_cutoff": fmt(p_end),
            "current_period_knowledge": fmt(p_end),

            "prior_period_start": fmt(prior_start),
            "prior_period_cutoff": fmt(prior_end),
            "prior_period_knowledge": fmt(prior_end),
        }

        records.append(rec)
        prev_start, prev_end = p_start, p_end

    write_calendar(portfolio, cadence, records)


if __name__ == "__main__":
    portfolio = "Portfolio1"

    history_start = datetime(2021, 1, 1, 0, 0, 0)
    history_end = datetime(2025, 12, 31, 23, 59, 59)

    for cadence in ("Daily", "Monthly", "Quarterly"):
        build_calendar(
            portfolio,
            cadence,
            history_start,
            history_end,
        )
