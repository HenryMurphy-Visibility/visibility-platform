import csv
import os
import json
import pickle
from collections import defaultdict

from kernel_utilities import from_csv_date_to_app

BASE_PATH = "C:/Users/hjmne/PycharmProjects/chest"


def split_marks_by_period(portfolio: str, calendar: str):
    """
    ONE-TIME UTILITY

    Reads:
      - Global marks CSV

    Writes:
      - Per-period PKL files:
        funds/{portfolio}/Events/Marks/{period_name}.pkl

    Guarantees on output PKLs:
      - ALL date fields are datetime
      - tranid is int
      - Deterministic, runtime-safe
      - No CSV parsing required downstream
    """

    # --------------------------------------------------
    # Paths
    # --------------------------------------------------
    marks_path = (
        f"{BASE_PATH}/funds/{portfolio}/Events/{portfolio}.csv"
    )

    calendar_path = (
        f"{BASE_PATH}/funds/{portfolio}/Calendars/{calendar}/{calendar}.txt"
    )

    marks_out_dir = (
        f"{BASE_PATH}/funds/{portfolio}/Events/RegularTrades"
    )
    os.makedirs(marks_out_dir, exist_ok=True)

    # --------------------------------------------------
    # Load calendar records
    # --------------------------------------------------
    calendar_records = []
    with open(calendar_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("{"):
                calendar_records.append(json.loads(line))

    # --------------------------------------------------
    # Build period knowledge windows (datetime)
    # --------------------------------------------------
    periods = []
    for r in calendar_records:
        periods.append({
            "period_name": r["period_name"],
            "start": from_csv_date_to_app(
                r["prior_period_knowledge"],
                field_name="calendar.prior_period_knowledge",
            ),
            "end": from_csv_date_to_app(
                r["current_period_knowledge"],
                field_name="calendar.current_period_knowledge",
            ),
        })

    # --------------------------------------------------
    # Read marks CSV ONCE
    # --------------------------------------------------
    with open(marks_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    buckets = defaultdict(list)

    EVENT_DATE_COLS = (
        "tradedate",
        "settledate",
        "kdbegin",
        "kdend",
        "knowledge_date",
    )

    # --------------------------------------------------
    # Bucket + NORMALIZE rows
    # --------------------------------------------------
    for r in rows:
        # Normalize ALL date fields
        for col in EVENT_DATE_COLS:
            if col in r and r[col]:
                r[col] = from_csv_date_to_app(
                    r[col],
                    field_name=f"event.{col}",
                )
            else:
                r[col] = None

        # Normalize tranid
        if "tranid" in r and r["tranid"] is not None:
            r["tranid"] = int(r["tranid"])

        kd = r["kdbegin"]

        if kd is None:
            continue

        for p in periods:
            if p["start"] < kd <= p["end"]:
                buckets[p["period_name"]].append(r)
                break

    # --------------------------------------------------
    # Write per-period PKL files
    # --------------------------------------------------
    for period_name, period_rows in buckets.items():
        if not period_rows:
            continue

        out_path = f"{marks_out_dir}/{period_name}.pkl"

        with open(out_path, "wb") as f:
            pickle.dump(period_rows, f, protocol=pickle.HIGHEST_PROTOCOL)

        print(f"✔ Wrote {len(period_rows):,} marks → {out_path}")

    print("✅ Mark split complete (PKL, normalized).")


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    portfolio = "Portfolio1"
    calendar = "Monthly"

    print(f"🔧 Splitting marks for {portfolio} / {calendar}")
    split_marks_by_period(portfolio, calendar)
    print("✅ Done.")


if __name__ == "__main__":
    main()





# import pickle
#
# pkl_path = (
#     "C:/Users/hjmne/PycharmProjects/chest/"
#     "funds/Portfolio1/Calendars/Monthly/"
#     "Periods/2021-07/Outputs/Journals/period_journals.pkl"
# )
#
#
# with open(pkl_path, "rb") as f:
#     data = pickle.load(f)
# print("TYPE:", type(data))
#
# if isinstance(data, list):
#     je = data[0]
# else:
#     je = data
#
#
#
# def debug_print_je(obj, label="JE"):
#     print(f"\n===== DEBUG {label} =====")
#     print("TYPE:", type(obj))
#
#     # Case 1: dict
#     if isinstance(obj, dict):
#         print("DICT KEYS:")
#         for k in sorted(obj.keys()):
#             print(" ", k)
#         return
#
#     # Case 2: list
#     if isinstance(obj, list):
#         print("LIST LENGTH:", len(obj))
#         if obj:
#             debug_print_je(obj[0], label=f"{label}[0]")
#         return
#
#     # Case 3: object with __dict__
#     if hasattr(obj, "__dict__"):
#         print("OBJECT ATTRIBUTES:")
#         for k in sorted(obj.__dict__.keys()):
#             v = obj.__dict__[k]
#             print(f"  {k}: {type(v)}")
#         return
#
#     # Case 4: totally opaque
#     print("OPAQUE OBJECT – dir():")
#     for name in dir(obj):
#         if not name.startswith("_"):
#             print(" ", name)
