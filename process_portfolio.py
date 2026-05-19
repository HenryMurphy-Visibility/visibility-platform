# ============================================================
# process_portfolio.py
# Visibility — Central Processing Hub Entry Point
#
# Caller-agnostic portfolio processing module.
# Used by: GWI, REST API, Watchdog, CLI
#
# Public functions:
#   bootstrap_portfolio()  — build portfolio world from global master
#   run_period()           — process a single period
#   run_all_periods()      — process all periods for a calendar
#   get_events_cached()    — load events with session cache
#   clear_event_cache()    — invalidate cache (called by Watchdog)
#
# Henry J. Murphy — Chest Financial Systems
# ============================================================

import json
import os
import csv
import pickle
import time
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional

from v_config import BASE_PATH, FUNDS_PATH, REFDATA_PATH

# ============================================================
# EVENT CACHE
# Keyed by portfolio — events loaded once per server session.
# Cache persists until explicitly cleared (e.g. when new
# events arrive via Watchdog).
# ============================================================

_EVENT_CACHE: dict = {}


def get_events_cached(portfolio: str) -> list:
    """
    Load all events for a portfolio using session cache.
    First call reads from disk — subsequent calls return instantly.
    Called by run_all_periods — replaces direct CSV loading.
    """
    if portfolio in _EVENT_CACHE:
        print(f">>> EVENT CACHE HIT  | {portfolio} | "
              f"{len(_EVENT_CACHE[portfolio])} events")
        return _EVENT_CACHE[portfolio]

    from kernel_utilities import load_events_csv_to_app

    print(f">>> EVENT CACHE MISS | {portfolio} | loading from disk...")

    events_path = _events_path(portfolio)
    marks_path  = _marks_path(portfolio)

    if not events_path.exists():
        raise RuntimeError(f"Events file not found: {events_path}")

    # ── LOAD REGULAR EVENTS ───────────────────────────────────────
    regular_events = load_events_csv_to_app(str(events_path))

    # ── LOAD MARKS — graceful if missing or empty ─────────────────
    if marks_path.exists():
        with open(marks_path, newline="") as f:
            reader = csv.DictReader(f)
            rows   = list(reader)
        if rows:
            mark_events = load_events_csv_to_app(str(marks_path))
        else:
            print(f">>> MARKS EMPTY | {portfolio} | continuing with no marks")
            mark_events = []
    else:
        print(f">>> MARKS NOT FOUND | {portfolio} | continuing with no marks")
        mark_events = []

    all_events = regular_events + mark_events

    _EVENT_CACHE[portfolio] = all_events

    print(f">>> EVENT CACHE SET  | {portfolio} | "
          f"{len(regular_events)} regular | "
          f"{len(mark_events)} marks | "
          f"{len(all_events)} total")

    return all_events


def clear_event_cache(portfolio: str = None) -> None:
    """
    Clear the event cache.
    portfolio=None clears all portfolios.
    Called by Watchdog when new events arrive.
    """
    global _EVENT_CACHE
    if portfolio:
        if portfolio in _EVENT_CACHE:
            del _EVENT_CACHE[portfolio]
            print(f">>> EVENT CACHE CLEARED | {portfolio}")
    else:
        _EVENT_CACHE = {}
        print(">>> EVENT CACHE CLEARED | all portfolios")


# ============================================================
# PATHS
# ============================================================

def _portfolio_dir(portfolio: str) -> Path:
    return Path(FUNDS_PATH) / portfolio

def _events_path(portfolio: str) -> Path:
    return _portfolio_dir(portfolio) / "Events" / f"{portfolio}.csv"

def _marks_path(portfolio: str) -> Path:
    return _portfolio_dir(portfolio) / "Events" / f"{portfolio}_marks.csv"

def _calendar_path(portfolio: str, calendar: str) -> Path:
    return _portfolio_dir(portfolio) / "Calendars" / calendar / f"{calendar}.txt"

def _snapshots_dir(portfolio: str, calendar: str) -> Path:
    return _portfolio_dir(portfolio) / "Calendars" / calendar / "Snapshots"

def _refdata_dir(portfolio: str) -> Path:
    return _portfolio_dir(portfolio) / "RefData"

def _candidates_dir(portfolio: str) -> Path:
    return _portfolio_dir(portfolio) / "Candidates"

def _global_im_path() -> Path:
    return Path(REFDATA_PATH) / "investment_master.csv"

def _global_bi_path() -> Path:
    return Path(REFDATA_PATH) / "bond_info.csv"


# ============================================================
# BOOTSTRAP — build portfolio world from global master
# ============================================================

def bootstrap_portfolio(portfolio: str, force: bool = False) -> dict:
    """
    Build the self-contained portfolio world.

    Steps:
      1. Derive candidate investments from event history
      2. Extract portfolio-specific IM from global master
      3. Extract portfolio-specific bond info from global bond info
      4. Save candidates.json
      5. Create marks file from price/fx master

    Parameters
    ----------
    portfolio : Portfolio identifier e.g. "Portfolio1"
    force     : If True, rebuild even if candidates.json exists
    """

    print(f"\n>>> BOOTSTRAP | {portfolio}")

    candidates_path = _candidates_dir(portfolio) / "candidates.json"

    # Skip if already built and not forced
    if candidates_path.exists() and not force:
        with open(candidates_path) as f:
            existing = json.load(f)
        print(f">>> BOOTSTRAP | {portfolio} | already built | "
              f"{existing.get('count', 0)} investments | skipping")

        # Still build marks if missing — marks file may not have been created
        marks_path = _marks_path(portfolio)
        if not marks_path.exists() or os.path.getsize(marks_path) == 0:
            print(f">>> BOOTSTRAP | {portfolio} | marks missing — rebuilding")
            from kernel_utilities import from_csv_date_to_app_new
            first_trade_dates = {}
            events_path = _events_path(portfolio)
            if events_path.exists():
                with open(events_path, newline="") as f:
                    for row in csv.DictReader(f):
                        inv = (row.get("investment") or "").strip()
                        td_raw = (row.get("tradedate") or "").strip()
                        if inv and td_raw:
                            try:
                                td = from_csv_date_to_app_new(td_raw)
                                if inv not in first_trade_dates or td < first_trade_dates[inv]:
                                    first_trade_dates[inv] = td
                            except Exception:
                                pass
            _create_marks(portfolio, first_trade_dates)

        return {
            "candidates": set(existing.get("investments", [])),
            "currencies": set(existing.get("currencies", [])),
            "investment_count": existing.get("count", 0),
            "bond_count": 0,
        }

    # ── 1. DERIVE CANDIDATES FROM EVENTS ─────────────────────────
    events_path = _events_path(portfolio)
    if not events_path.exists():
        raise RuntimeError(f"Events file not found: {events_path}")

    candidates        = set()
    currencies        = set()
    first_trade_dates = {}   # investment → earliest tradedate (datetime)

    with open(events_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            inv = (row.get("investment") or "").strip()
            if inv:
                candidates.add(inv)
                td_raw = (row.get("tradedate") or "").strip()
                if td_raw:
                    try:
                        from kernel_utilities import from_csv_date_to_app_new
                        td = from_csv_date_to_app_new(td_raw)
                        if inv not in first_trade_dates or td < first_trade_dates[inv]:
                            first_trade_dates[inv] = td
                    except Exception:
                        pass

            for col in ["payment_currency", "buy_currency", "sell_currency"]:
                val = (row.get(col) or "").strip()
                if val and val != "0":
                    currencies.add(val)

    # Currencies are also investments
    candidates.update(currencies)

    print(f">>> BOOTSTRAP | {portfolio} | {len(candidates)} candidates | "
          f"{len(currencies)} currencies")

    # ── 2. EXTRACT PORTFOLIO IM ───────────────────────────────────
    investment_count = _extract_portfolio_im(portfolio, candidates)

    # ── 3. EXTRACT PORTFOLIO BOND INFO ───────────────────────────
    bond_count = _extract_portfolio_bond_info(portfolio)

    # ── 4. SAVE CANDIDATES ────────────────────────────────────────
    _candidates_dir(portfolio).mkdir(parents=True, exist_ok=True)
    with open(candidates_path, "w") as f:
        json.dump({
            "portfolio":    portfolio,
            "last_updated": datetime.now().isoformat(),
            "count":        len(candidates),
            "investments":  sorted(candidates),
            "currencies":   sorted(currencies),
        }, f, indent=2)

    # ── 5. CREATE MARKS ───────────────────────────────────────────
    marks_count = _create_marks(portfolio, first_trade_dates)

    print(f">>> BOOTSTRAP COMPLETE | {portfolio} | "
          f"{investment_count} IM records | {bond_count} bond records | "
          f"{marks_count} marks created")

    return {
        "candidates":       candidates,
        "currencies":       currencies,
        "investment_count": investment_count,
        "bond_count":       bond_count,
        "marks_count":      marks_count,
    }


def _create_marks(portfolio: str, first_trade_dates: dict) -> int:
    """
    Create the marks file for a portfolio from price/fx master.
    Calls create_portfolio_marks from core_ingest_loaders.

    Skips if marks file already has content (not just a header).
    Use force=True in bootstrap_portfolio to rebuild.
    """
    marks_path = _marks_path(portfolio)

    # Skip if marks already populated
    if marks_path.exists():
        with open(marks_path, newline="") as f:
            reader = csv.DictReader(f)
            rows   = list(reader)
            if rows:
                print(f"    Marks: already present ({len(rows)} rows) — skipping")
                return len(rows)

    if not first_trade_dates:
        print(f"    Marks: no events to derive marks from — skipping")
        return 0

    try:
        from core_ingest_loaders import create_portfolio_marks

        # Build candidates dict: {(portfolio, investment): first_trade_date}
        candidates_dict = {
            (portfolio, inv): td
            for inv, td in first_trade_dates.items()
        }

        history_start = min(first_trade_dates.values())
        history_end   = date.today()

        print(f"    Marks: building from {history_start} → {history_end} "
              f"for {len(candidates_dict)} investments...")

        marks_count = create_portfolio_marks(
            portfolio     = portfolio,
            candidates    = candidates_dict,
            history_start = history_start,
            history_end   = history_end,
        )

        print(f"    Marks: {marks_count} marks created")
        return marks_count

    except ImportError as e:
        print(f"    Marks: WARNING — could not import core_ingest_loaders: {e}")
        return 0
    except Exception as e:
        print(f"    Marks: WARNING — marks creation failed: {e}")
        import traceback
        traceback.print_exc()
        return 0


def _extract_portfolio_im(portfolio: str, candidates: set) -> int:
    """Extract portfolio-specific IM from global master."""

    global_path  = _global_im_path()
    portfolio_im = _refdata_dir(portfolio) / "investment_master.csv"

    if not global_path.exists():
        print(f"    WARNING: Global IM not found at {global_path}")
        return 0

    _refdata_dir(portfolio).mkdir(parents=True, exist_ok=True)

    existing = set()
    if portfolio_im.exists():
        with open(portfolio_im, newline="") as f:
            for row in csv.DictReader(f):
                inv = row.get("investment", "").strip()
                if inv:
                    existing.add(inv)

    needed = candidates - existing
    if not needed:
        print(f"    IM: already complete ({len(existing)} records)")
        return len(existing)

    with open(global_path, newline="") as f:
        global_rows = list(csv.DictReader(f))

    inv_col = _find_inv_col(global_rows[0] if global_rows else {})
    if not inv_col:
        print(f"    WARNING: Cannot find investment column in global IM")
        return 0

    global_map = {r[inv_col].strip(): r for r in global_rows if r.get(inv_col)}
    missing    = needed - global_map.keys()

    if missing:
        raise RuntimeError(
            f"BOOTSTRAP FAILED — {len(missing)} investment(s) not found "
            f"in global investment master: {sorted(missing)}. "
            f"Add to global IM before processing."
        )

    to_write  = [global_map[inv] for inv in needed if inv in global_map]
    write_hdr = not portfolio_im.exists()

    if to_write:
        fieldnames = list(global_rows[0].keys()) if global_rows else []
        with open(portfolio_im, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_hdr:
                writer.writeheader()
            writer.writerows(to_write)

    total = len(existing) + len(to_write)
    print(f"    IM: {len(to_write)} new records added → {total} total")
    return total


def _extract_portfolio_bond_info(portfolio: str) -> int:
    """Extract portfolio-specific bond info from global bond info."""

    global_path  = _global_bi_path()
    portfolio_im = _refdata_dir(portfolio) / "investment_master.csv"
    portfolio_bi = _refdata_dir(portfolio) / "bond_info.csv"

    if not global_path.exists():
        print(f"    Bond info: global file not found — skipping")
        return 0

    if not portfolio_im.exists():
        print(f"    Bond info: portfolio IM not found — skipping")
        return 0

    bonds = set()
    with open(portfolio_im, newline="") as f:
        for row in csv.DictReader(f):
            inv_type = (
                row.get("investment_type") or
                row.get("Investment_Type") or ""
            ).upper().strip()
            if inv_type == "BOND":
                inv = row.get("investment", "").strip()
                if inv:
                    bonds.add(inv)

    if not bonds:
        print(f"    Bond info: no bonds in portfolio IM")
        return 0

    existing = set()
    if portfolio_bi.exists():
        with open(portfolio_bi, newline="") as f:
            for row in csv.DictReader(f):
                inv = row.get("investment", "").strip()
                if inv:
                    existing.add(inv)

    needed = bonds - existing
    if not needed:
        print(f"    Bond info: already complete ({len(existing)} records)")
        return len(existing)

    with open(global_path, newline="") as f:
        global_rows = list(csv.DictReader(f))

    global_map = {r.get("investment", "").strip(): r for r in global_rows}
    to_write   = [global_map[b] for b in needed if b in global_map]
    write_hdr  = not portfolio_bi.exists()

    if to_write:
        fieldnames = list(global_rows[0].keys()) if global_rows else []
        with open(portfolio_bi, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_hdr:
                writer.writeheader()
            writer.writerows(to_write)

    total = len(existing) + len(to_write)
    print(f"    Bond info: {len(to_write)} new records → {total} total")
    return total


def _find_inv_col(row: dict) -> Optional[str]:
    """Find the investment column regardless of name."""
    for col in ["investment", "ticker", "Investment", "Ticker", "TICKER"]:
        if col in row:
            return col
    return None


# ============================================================
# RUN PERIOD — process a single period
# ============================================================

def run_period(
    portfolio:        str,
    calendar:         str,
    period_name:      str,
    all_events:       list,
    calendar_records: list,
) -> dict:
    """
    Process a single accounting period.
    Caller is responsible for providing events and calendar records.

    Boundary rules:
      - kdbegin <= current_period_knowledge  (inclusive — ties belong here)
      - tradedate <= current_period_cutoff   (inclusive — ties belong here)
      - tradedate > replay_start             (exclusive — already processed)
      - First period: replay_start shifted back 1 day so inception-day
        trades pass the > filter.
    """

    from central_processing_hub import cph_run_and_materialize
    from kernel_utilities import from_csv_date_to_app_new

    records = [r for r in calendar_records if r["period_name"] == period_name]
    if not records:
        raise RuntimeError(f"Period not found: {period_name}")
    rec = records[0]

    per_period_ctx = {
        "portfolio":                portfolio,
        "calendar":                 calendar,
        "period_name":              rec["period_name"],
        "prior_period_start":       from_csv_date_to_app_new(rec["prior_period_start"]),
        "prior_period_cutoff":      from_csv_date_to_app_new(rec["prior_period_cutoff"]),
        "prior_period_knowledge":   from_csv_date_to_app_new(rec["prior_period_knowledge"]),
        "current_period_start":     from_csv_date_to_app_new(rec["current_period_start"]),
        "current_period_cutoff":    from_csv_date_to_app_new(rec["current_period_cutoff"]),
        "current_period_knowledge": from_csv_date_to_app_new(rec["current_period_knowledge"]),
    }

    newly_known = [
        e for e in all_events
        if (
            e["kdbegin"] > per_period_ctx["prior_period_knowledge"]
            and e["kdbegin"] <= per_period_ctx["current_period_knowledge"]
        )
    ]

    earliest_trade_date = (
        min(e["tradedate"] for e in newly_known)
        if newly_known else None
    )

    snapshots_dir          = _snapshots_dir(portfolio, calendar)
    selected_snapshot_path = None
    selected_snapshot_kd   = None

    if earliest_trade_date and snapshots_dir.exists():
        for fn in snapshots_dir.iterdir():
            if fn.suffix != ".pkl":
                continue
            try:
                snapshot_kd = datetime.strptime(fn.stem, "%Y-%m-%dT%H-%M-%S")
            except Exception:
                continue
            if snapshot_kd < earliest_trade_date:
                if selected_snapshot_kd is None or snapshot_kd > selected_snapshot_kd:
                    selected_snapshot_kd   = snapshot_kd
                    selected_snapshot_path = fn

    # ── is_first defined before replay_start — needed for inception fix ──
    is_first = (period_name == calendar_records[0]["period_name"])

    replay_start = (
        selected_snapshot_kd
        if selected_snapshot_kd is not None
        else per_period_ctx["prior_period_knowledge"]
    )

    # First period: prior_period_knowledge == inception date.
    # Shift back one day so inception-day trades pass the > filter.
    if is_first:
        replay_start = replay_start - timedelta(days=1)

    # Boundary rule: ties are INCLUSIVE on knowledge and cutoff.
    # replay_start is the only exclusive boundary — already processed.
    event_pool = [
        e for e in all_events
        if (
            e["tradedate"] > replay_start
            and e["kdbegin"] <= per_period_ctx["current_period_knowledge"]
            and e["tradedate"] <= per_period_ctx["current_period_cutoff"]
        )
    ]

    print(
        f"\n>>> RUN PERIOD | {portfolio} | {period_name} | "
        f"{len(event_pool)} events | "
        f"snapshot={'yes' if selected_snapshot_path else 'cold'}",
        flush=True
    )

    metrics = cph_run_and_materialize(
        portfolio=portfolio,
        calendar=calendar,
        per_period_ctx=per_period_ctx,
        snapshot_path=selected_snapshot_path,
        replay_start=replay_start,
        events=event_pool,
        is_first_calendar_period=is_first,
    )

    return metrics


# ============================================================
# RUN ALL PERIODS — process all periods for a calendar
# ============================================================

def run_all_periods(
    portfolio:   str,
    calendar:    str,
    period_name: Optional[str] = None,
) -> list:
    """
    Process all periods (or a single period) for a portfolio/calendar.

    Uses event cache — events loaded once per server session.
    Subsequent calls for the same portfolio are instant.
    """

    from kernel_utilities import from_csv_date_to_app

    print(f"\n>>> RUN ALL PERIODS | {portfolio} | {calendar}")

    # ── LOAD CALENDAR ─────────────────────────────────────────────
    cal_path = _calendar_path(portfolio, calendar)
    if not cal_path.exists():
        raise RuntimeError(f"Calendar file not found: {cal_path}")

    calendar_records = []
    with open(cal_path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or not ln.startswith("{"):
                continue
            try:
                calendar_records.append(json.loads(ln))
            except json.JSONDecodeError:
                continue

    if not calendar_records:
        raise RuntimeError(f"No calendar records in {cal_path}")

    # ── SELECT PERIODS ────────────────────────────────────────────
    if period_name:
        records_to_process = [
            r for r in calendar_records
            if r["period_name"] == period_name
        ]
        if not records_to_process:
            raise RuntimeError(f"Period not found: {period_name}")
    else:
        records_to_process = calendar_records

    # ── LOAD EVENTS — CACHED ──────────────────────────────────────
    all_events = get_events_cached(portfolio)

    # ── PROCESS PERIODS ───────────────────────────────────────────
    all_metrics = []

    for rec in records_to_process:
        metrics = run_period(
            portfolio=portfolio,
            calendar=calendar,
            period_name=rec["period_name"],
            all_events=all_events,
            calendar_records=calendar_records,
        )
        all_metrics.append(metrics)

    # ── SUMMARY ───────────────────────────────────────────────────
    print(f"\n>>> RUN COMPLETE | {portfolio} | {calendar}")
    for m in all_metrics:
        print(
            f"    {m.get('period_name', '?')} | "
            f"regular={m.get('regular_journal_entries', 0)} | "
            f"adjusting={m.get('adjusting_journal_entries', 0)} | "
            f"time={m.get('total_time', 0):.3f}s"
        )

    return all_metrics


# ============================================================
# CLI ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python process_portfolio.py <portfolio> <calendar> [period_name]")
        sys.exit(1)

    portfolio   = sys.argv[1]
    calendar    = sys.argv[2]
    period_name = sys.argv[3] if len(sys.argv) > 3 else None

    bootstrap_portfolio(portfolio)
    metrics = run_all_periods(portfolio, calendar, period_name)
    print(f"\nDone. {len(metrics)} period(s) processed.")