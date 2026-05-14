import json
import time
import traceback
from pathlib import Path

from bookkeeping import EventScheduler, BookkeepingSpace
from central_processing_hub import cph_run_and_materialize
from core_scheduling import core_schedule_events

# ============================================================
# DIRECTORY SAFETY
# ============================================================

def ensure_period_output_dirs(
    *,
    portfolio: str,
    calendar: str,
    period_name: str,
):
    base = (
        Path("C:/Users/hjmne/PycharmProjects/chest/funds")
        / portfolio
        / "Calendars"
        / calendar
        / "Periods"
        / period_name
        / "Outputs"
    )

    snapshots_dir = base / "Snapshots"
    journals_dir  = base / "Journals"

    snapshots_dir.mkdir(parents=True, exist_ok=True)
    journals_dir.mkdir(parents=True, exist_ok=True)

    return snapshots_dir, journals_dir


# ============================================================
# CALENDAR RECORD ITERATION (AUTHORITATIVE FILE READ)
# ============================================================

def iterate_through_calendar_records(portfolio, calendar):
    """
    READ calendar file and return records IN FILE ORDER.
    No normalization. No inference. No filtering.
    """

    cal_path = (
        Path("C:/Users/hjmne/PycharmProjects/chest/funds")
        / portfolio
        / "Calendars"
        / calendar
        / f"{calendar}.txt"
    )

    if not cal_path.exists():
        raise FileNotFoundError(f"Calendar file not found: {cal_path}")

    records = []

    with open(cal_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            if line.lower().startswith("calendar"):
                continue
            if not line.startswith("{"):
                continue

            records.append(json.loads(line))

    if not records:
        raise RuntimeError("No calendar records found")

    return records


# ============================================================
# CALENDAR-DRIVEN SERIAL EXECUTION
# ============================================================

def run_calendar_serial(
    *,
    portfolio,
    calendar,
    mode,
    stop_on_error=True,
):
    """
    Calendar-driven SERIAL execution.

    For each calendar record:
        - fresh bookkeeping space
        - ingest
        - schedule
        - sort
        - CPH
    """

    records = iterate_through_calendar_records(portfolio, calendar)

    print(
        f"[RUN_CALENDAR_SERIAL] portfolio={portfolio} "
        f"calendar={calendar} mode={mode} "
        f"periods={len(records)}"
    )

    for rec in records:
        period_name = rec["period_name"]

        print(f"\n▶ Processing period: {period_name}")

        # --------------------------------------------------
        # PER-PERIOD RUNTIME RESET (REQUIRED)
        # --------------------------------------------------
        t0_total = time.perf_counter()
        stats = {}

        ensure_period_output_dirs(
            portfolio=portfolio,
            calendar=calendar,
            period_name=period_name,
        )

        space = BookkeepingSpace()

        # --------------------------------------------------
        # INGEST
        # --------------------------------------------------
        events_for_scheduler, all_events, interpretation_ctx = ingest(
            portfolio=portfolio,
            calendar=calendar,
            period_name=period_name,
            space=space,
        )

        # --------------------------------------------------
        # SCHEDULER
        # --------------------------------------------------
        scheduler = EventScheduler(space)

        core_schedule_events(
            interpretation_ctx,
            events_for_scheduler,
            space,
            scheduler,
        )

        scheduler.sort_events()

        # --------------------------------------------------
        # CPH
        # --------------------------------------------------
        t0 = time.perf_counter()

        try:
            cph_run_and_materialize(
                space=space,
                scheduler=scheduler,
                interpretation_ctx=interpretation_ctx,
                portfolio=portfolio,
                calendar=calendar,
                period_name=period_name,
                events_for_scheduler=events_for_scheduler,
                mode=mode,
            )

            stats["cph_time"] = time.perf_counter() - t0
            stats["total_time"] = time.perf_counter() - t0_total

            print(
                f"✔ Completed {period_name} "
                f"in {stats['total_time']:.2f}s"
            )

        except Exception as e:
            print(f"\n❌ ERROR in period '{period_name}': {e}")
            traceback.print_exc()

            if stop_on_error:
                raise

            print("⚠ Continuing to next period…")

   # ==================================================
        # ✅ END-OF-PERIOD HARD RESET (THIS IS THE ANSWER)
        # ==================================================
        scheduler = None
        space = None
        interpretation_ctx = None
        events_for_scheduler = None
        all_events = None
        stats = None


# ============================================================
# ENTRY POINT (PYCHARM-FRIENDLY)
# ============================================================

if __name__ == "__main__":

    PORTFOLIO = "Portfolio1"
    CALENDAR  = "Monthly"        # name only, NOT .txt
    MODE      = "snapshot_view"  # or "closed_period"
    STOP_ON_ERROR = True

    run_calendar_serial(
        portfolio=PORTFOLIO,
        calendar=CALENDAR,
        mode=MODE,
        stop_on_error=STOP_ON_ERROR,
    )
