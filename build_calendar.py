import os
import json
from datetime import datetime, timedelta, time

# ============================================================
# LOCKED CALENDAR SEMANTICS
# ============================================================

BUSINESS_CLOSE_TIME = time(23, 59, 59)
BUSINESS_START_OFFSET = timedelta(seconds=1)
DATE_FMT = "%Y-%m-%d:%H:%M:%S"

# ============================================================
# DATE HELPERS
# ============================================================

def fmt(dt):
    return dt.strftime(DATE_FMT)

# ============================================================
# BUSINESS DAY HELPERS
# ============================================================

def is_business_day(dt):
    return dt.weekday() < 5  # Mon–Fri

def prev_business_day(dt):
    cur = dt - timedelta(days=1)
    while not is_business_day(cur):
        cur -= timedelta(days=1)
    return cur

# ============================================================
# DAILY CALENDAR CREATION
# ============================================================

def build_daily_calendar(
    start_date,
    end_date,
    output_dir,
    file_name,
):
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, file_name)

    records = []

    cur = start_date
    while cur <= end_date:

        # Skip weekends entirely
        if not is_business_day(cur):
            cur += timedelta(days=1)
            continue

        prior_bd = prev_business_day(cur)

        prior_cutoff = datetime.combine(
            prior_bd.date(), BUSINESS_CLOSE_TIME
        )
        current_cutoff = datetime.combine(
            cur.date(), BUSINESS_CLOSE_TIME
        )

        record = {
            "period_name": cur.strftime("%Y-%m-%d"),
            "period_status": "Pending",

            # CURRENT
            "current_period_start": fmt(
                prior_cutoff + BUSINESS_START_OFFSET
            ),
            "current_period_cutoff": fmt(current_cutoff),
            "current_period_knowledge": fmt(current_cutoff),

            # PRIOR
            "prior_period_start": fmt(
                prior_cutoff + BUSINESS_START_OFFSET
            ),
            "prior_period_cutoff": fmt(prior_cutoff),
            "prior_period_knowledge": fmt(prior_cutoff),
        }

        records.append(record)
        cur += timedelta(days=1)

    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    return output_path, len(records)

# ============================================================
# MAIN — EDIT ONLY HERE
# ============================================================

def main():
    START_DATE = "2021-01-01"
    END_DATE   = "2025-12-31"

    OUTPUT_DIR = (
        "C:/Users/hjmne/PycharmProjects/chest/"
        "funds/Portfolio1/Calendars/Daily"
    )

    FILE_NAME = "Daily.txt"

    start_date = datetime.strptime(START_DATE, "%Y-%m-%d")
    end_date = datetime.strptime(END_DATE, "%Y-%m-%d")

    path, count = build_daily_calendar(
        start_date=start_date,
        end_date=end_date,
        output_dir=OUTPUT_DIR,
        file_name=FILE_NAME,
    )

    print("✔ Daily calendar creation complete")
    print(f"  Records written : {count}")
    print(f"  Output file     : {path}")

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
