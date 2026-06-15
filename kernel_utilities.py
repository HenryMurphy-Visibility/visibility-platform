# ============================================================
# chest/kernel_utilities.py
# ============================================================
"""
VISIBILITY KERNEL UTILITIES
==========================

Authoritative kernel-level utilities for the Visibility application.

This module is the SINGLE source of truth for:
- Boundary crossings (disk → app, pickle → app, app → disk)
- Temporal normalization
- Execution-state assertions
- Scheduling and processing readiness
- Snapshot admissibility

PHILOSOPHY
----------
Nothing enters application state without passing through the kernel.

CSV / JSON     → dumb, string-based
Pickle         → binary, typed, internal
Application    → strict, validated, executable

This file is intentionally LARGE and CENTRALIZED.
Kernel code should be boring, explicit, and final.

DO NOT:
- Add business logic
- Add domain rules
- Add UI logic
- Add persistence logic

This is infrastructure.
"""


from typing import Iterable, Any
import datetime
import pandas as pd

# ============================================================
# SECTION 0 — CANONICAL CONSTANTS
# ============================================================

_CANONICAL_TIME = datetime.time(0, 0, 0)

def revenue_expense_rows(state):
    rows = []
    repo = state["revenue_expense_repository"]["investment_spaces_library"]

    for _, subspace in repo.items():
        for (
            portfolio,
            investment,
            lotid,
            tax_date,
            ls,
            location,
            financial_account
        ), (qty, local, book, *_rest) in subspace.entries.items():

            rows.append({
                "portfolio": portfolio,
                "investment": investment,
                "lotid": lotid,
                "tax_date": tax_date,
                "ls": ls,
                "location": location,
                "financial_account": financial_account,
                "quantity": qty,
                "local": local,
                "book": book,
            })

    return pd.DataFrame(rows)

def kernel_guard(phase: str):
    """
    INTENT:
        Context manager to provide phase-aware diagnostics
        for ingest / scheduling / processing.

    USAGE:
        with kernel_guard("INGEST: LOAD CALENDAR"):
            ...

    FAILURE MODE:
        - Prints phase context
        - Re-raises original exception
    """
    class _KernelGuard:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            if exc is not None:
                print("\n=================================================")
                print(f"❌ KERNEL FAILURE DURING PHASE: {phase}")
                print("-------------------------------------------------")
                print(f"Exception: {exc}")
                print("-------------------------------------------------")
                import traceback
                traceback.print_tb(tb)
                print("=================================================\n")
                return False  # re-raise

    return _KernelGuard()

# kernel_utilities.py

def project_events_for_period(
    *,
    all_events,
    replay_start,           # from snapshot or inception
    accounting_cutoff,      # current_period_cutoff
    knowledge_cutoff,       # current_period_knowledge
):
    qualifying = []

    for e in all_events:
        # Knowledge window (hard gate)
        if e["kdbegin"] > knowledge_cutoff:
            continue

        # Economic replay window (hard gate)
        if replay_start is not None and e["tradedate"] < replay_start:
            continue

        # Accounting window (hard gate)
        if e["tradedate"] <= accounting_cutoff:
            qualifying.append(e)

    return qualifying


from datetime import datetime

_CANONICAL_TIME = datetime.min.time()

def csv_date_to_app(value, *, field_name: str) -> datetime:
    """
    Convert external / CSV date values into canonical Visibility datetime.

    ACCEPTED INPUTS:
        - datetime
        - 'MM/DD/YYYY:HH:MM:SS'
        - 'YYYY-MM-DD:HH:MM:SS'
        - 'YYYY-MM-DD'

    OUTPUT:
        - datetime normalized to 00:00:00

    FAILURE:
        - Raises RuntimeError with field attribution
    """

    if value is None:
        raise RuntimeError(
            f"[DATE ERROR] field='{field_name}' value=None"
        )

    if isinstance(value, datetime):
        return datetime.combine(value.date(), _CANONICAL_TIME)

    if isinstance(value, str):
        v = value.strip()
        if not v:
            raise RuntimeError(
                f"[DATE ERROR] field='{field_name}' empty string"
            )

        try:
            if "/" in v:
                dt = datetime.strptime(v, "%m/%d/%Y:%H:%M:%S")
                return datetime.combine(dt.date(), _CANONICAL_TIME)

            if ":" in v:
                dt = datetime.strptime(v, "%Y-%m-%d:%H:%M:%S")
                return datetime.combine(dt.date(), _CANONICAL_TIME)

            dt = datetime.strptime(v, "%Y-%m-%d")
            return datetime.combine(dt.date(), _CANONICAL_TIME)

        except Exception as e:
            raise RuntimeError(
                f"[DATE ERROR] field='{field_name}' invalid format value='{value}'"
            ) from e

    raise RuntimeError(
        f"[DATE ERROR] field='{field_name}' unsupported type {type(value)}"
    )


def app_event_to_events_csv_row(event: dict) -> dict:
    """
    Convert an application-state event into a canonical EVENTS CSV row.
    """

    from datetime import datetime

    out = {}

    for k, v in event.items():
        if isinstance(v, datetime):
            out[k] = v.strftime("%m/%d/%Y:%H:%M:%S")
        else:
            out[k] = v

    return out


def assert_app_date(value, *, field_name: str):
    if not isinstance(value, datetime):
        raise RuntimeError(
            f"[KERNEL DATE ERROR] {field_name} must be datetime, got {value!r}"
        )


def assert_fx_rows(rows, *, context: str):
    for i, r in enumerate(rows):
        try:
            assert_app_date(r["date"], field_name="fx.date")
            if not isinstance(r["currency"], str):
                raise RuntimeError("currency must be str")
            if not isinstance(r["price"], (int, float)):
                raise RuntimeError("price must be numeric")
        except Exception as e:
            raise RuntimeError(
                f"[KERNEL FX ERROR] context={context} row={i} value={r} error={e}"
            )


def assert_price_rows(rows, *, context: str):
    for i, r in enumerate(rows):
        try:
            assert_app_date(r["date"], field_name="price.date")
            if not isinstance(r["ticker"], str):
                raise RuntimeError("ticker must be str")
            if not isinstance(r["price"], (int, float)):
                raise RuntimeError("price must be numeric")
        except Exception as e:
            raise RuntimeError(
                f"[KERNEL PRICE ERROR] context={context} row={i} value={r} error={e}"
            )


import datetime
from typing import Any

_CANONICAL_TIME = datetime.time(0, 0, 0)

def from_csv_date_to_app(value: Any, *, field_name: str) -> datetime:
    """
    Convert a CSV / external date value into canonical application datetime.

    ACCEPTED INPUTS:
        - 'MM/DD/YYYY:HH:MM:SS'     (PRIMARY CSV FORMAT)
        - 'YYYY-MM-DD'
        - 'YYYY-MM-DD:HH:MM:SS'
        - datetime

    OUTPUT:
        - datetime normalized to 00:00:00

    FAILURE MODE:
        - RuntimeError with field name and offending value
    """

    if value is None:
        raise RuntimeError(
            f"[KERNEL DATE ERROR] Field '{field_name}' is None"
        )

    # --------------------------------------------------
    # Already app-safe
    # --------------------------------------------------
    if isinstance(value, datetime):
        return datetime.combine(value.date(), _CANONICAL_TIME)

    # --------------------------------------------------
    # CSV / string inputs
    # --------------------------------------------------
    if isinstance(value, str):
        v = value.strip()

        if not v:
            raise RuntimeError(
                f"[KERNEL DATE ERROR] Field '{field_name}' is empty string"
            )

        try:
            # MM/DD/YYYY:HH:MM:SS  (canonical CSV format)
            if "/" in v:
                dt = datetime.strptime(v, "%m/%d/%Y:%H:%M:%S")
                return datetime.combine(dt.date(), _CANONICAL_TIME)

            # YYYY-MM-DD:HH:MM:SS
            if ":" in v:
                dt = datetime.strptime(v, "%Y-%m-%d:%H:%M:%S")
                return datetime.combine(dt.date(), _CANONICAL_TIME)

            # YYYY-MM-DD
            dt = datetime.strptime(v, "%Y-%m-%d")
            return datetime.combine(dt.date(), _CANONICAL_TIME)

        except Exception as e:
            raise RuntimeError(
                f"[KERNEL DATE ERROR] Field '{field_name}' invalid format: '{value}'"
            ) from e

    # --------------------------------------------------
    # Unsupported type
    # --------------------------------------------------
    raise RuntimeError(
        f"[KERNEL DATE ERROR] Field '{field_name}' unsupported type: {type(value)}"
    )

def load_csv_file_as_is(path: str):
    """
    LOAD CSV FILE AS-IS.

    Contract:
        - Reads CSV into a list of dicts
        - DOES NOT:
            - parse dates
            - coerce types
            - mutate values
            - validate schema
        - Returns raw string values exactly as stored on disk

    Responsibility:
        Disk → memory
        NOTHING MORE

    Any normalization, validation, or promotion
    MUST happen elsewhere (kernel boundary).
    """

    import os
    import csv

    if not os.path.exists(path):
        raise RuntimeError(f"[LOAD CSV AS-IS ERROR] File not found: {path}")

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]

    if not rows:
        raise RuntimeError(f"[LOAD CSV AS-IS ERROR] File is empty: {path}")

    return rows


def fx_rows_to_app(rows, *, context):
    out = []
    for i, r in enumerate(rows):
        try:
            out.append({
                "date": from_csv_date_to_app(r["date"], field_name="fx.date"),
                "currency": r["currency"],
                "price": float(r["price"]),
            })
        except Exception as e:
            raise RuntimeError(
                f"[KERNEL FX PROMOTION ERROR] context={context} row={i} value={r} error={e}"
            )
    return out

from datetime import datetime

def promote_price_date_to_app(value):
    """
    Promote a price / FX CSV date into Visibility app format.

    Input:
        '1/1/2021'  or '01/01/2021'

    Output:
        datetime(2021, 1, 1)

    This is intentionally DIFFERENT from event date promotion.
    """
    if value is None or value == "":
        raise ValueError("Price date is empty")

    try:
        # Visibility price/FX canonical format: M/D/YYYY
        return datetime.strptime(value, "%m/%d/%Y")
    except ValueError:
        raise ValueError(
            f"[KERNEL DATE ERROR] Field 'price.date' invalid format: '{value}'"
        )

def price_rows_to_app(rows, *, context):
    out = []
    for i, r in enumerate(rows):
        try:
            out.append({
                "date": promote_price_date_to_app(r["date"]),
                "ticker": r["ticker"],
                "currency": r["currency"],
                "price": float(r["price"]),
            })
        except Exception as e:
            raise RuntimeError(
                f"[KERNEL PRICE PROMOTION ERROR] context={context} row={i} value={r} error={e}"
            )
    return out


from datetime import datetime

def from_csv_date_to_app_new(value, *, field_name=None):
    if value in (None, ""):
        return None

    try:
        # Existing formats first
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            pass

        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

        # ✅ ADD THIS FORMAT
        try:
            return datetime.strptime(value, "%Y-%m-%d:%H:%M:%S")
        except ValueError:
            pass

        raise ValueError

    except Exception:
        raise RuntimeError(
            f"[CSV DATE PARSE ERROR] field={field_name} value={value}"
        )


def load_events_pkl_to_app(path: str):
    """
    Load pre-normalized events from a PKL file.

    Guarantees:
    - Events are already date-normalized
    - tranid already int
    - No filtering
    - No mutation
    - No side effects
    """

    import pickle
    import os

    if not os.path.exists(path):
        raise RuntimeError(f"[INGEST ERROR] Missing PKL event file: {path}")

    with open(path, "rb") as f:
        events = pickle.load(f)

    if not events:
        raise RuntimeError(f"[INGEST ERROR] Empty PKL event file: {path}")

    return events

def load_events_csv_to_app(path: str, allow_empty: bool = False):
    """
    Load EVENTS CSV and convert to application format.

    Guarantees on return:
      - All event date fields are datetime
      - tranid is int
      - Each event is classified as:
            - historical truth (already applied)
            - new knowledge (eligible for processing)
    """

    import csv
    import os


    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]

    if not rows:
        if allow_empty:
            return []
        raise RuntimeError(f"[INGEST ERROR] No events survived cutoff: {path}")

    EVENT_DATE_COLS = (
        "tradedate",
        "settledate",
        "kdbegin",
        "kdend",
        "knowledge_date",
    )

    for i, r in enumerate(rows):
        # -------------------------------
        # Normalize dates
        # -------------------------------
        for col in EVENT_DATE_COLS:
            if col in r and r[col]:
                r[col] = from_csv_date_to_app(
                    r[col],
                    field_name=f"event.{col}"
                )
            else:
                r[col] = None

        # -------------------------------
        # Normalize tranid
        # -------------------------------
        if "tranid" in r and r["tranid"] is not None:
            r["tranid"] = int(r["tranid"])
    return rows

def load_events_csv_to_app_with_cutoff(path: str, *, knowledge_cutoff_date, allow_empty: bool = False):
    """
    Load EVENTS CSV and apply knowledge cutoff BEFORE full normalization.

    Guarantees on return:
      - Only events with kdbegin <= knowledge_cutoff_date are materialized
      - All returned rows are fully normalized (dates, tranid)
    """

    import csv

    EVENT_DATE_COLS = (
        "tradedate",
        "settledate",
        "kdbegin",
        "kdend",
        "knowledge_date",
    )

    rows = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for raw in reader:
            # ----------------------------------
            # FAST PATH: parse ONLY kdbegin
            # ----------------------------------
            raw_kdbegin = raw.get("kdbegin")
            if not raw_kdbegin:
                continue

            kdbegin = from_csv_date_to_app(
                raw_kdbegin,
                field_name="event.kdbegin",
            )

            if kdbegin > knowledge_cutoff_date:
                continue  # 🚀 EARLY EXIT — NO FULL NORMALIZATION

            # ----------------------------------
            # FULL NORMALIZATION (SURVIVORS ONLY)
            # ----------------------------------
            r = dict(raw)

            for col in EVENT_DATE_COLS:
                if col in r and r[col]:
                    r[col] = from_csv_date_to_app(
                        r[col],
                        field_name=f"event.{col}",
                    )
                else:
                    r[col] = None

            if "tranid" in r and r["tranid"] is not None:
                r["tranid"] = int(r["tranid"])

            rows.append(r)

    if not rows:
        if allow_empty:
            return []
        raise RuntimeError(f"[INGEST ERROR] No events survived cutoff: {path}")

    return rows

def from_pickle_date_to_app(value: Any, *, field_name: str) -> datetime:
    """
    INTENT:
        Admit a pickled datetime into application state.

    RULE:
        Pickle MUST already contain datetime.

    FAILURE MODE:
        - RuntimeError if value is not datetime
    """
    if not isinstance(value, datetime):
        raise RuntimeError(
            f"[KERNEL PICKLE DATE ERROR] Field '{field_name}' must be datetime, "
            f"got {type(value)}"
        )

    return datetime.combine(value.date(), _CANONICAL_TIME)


# ============================================================
# SECTION 2 — DATE EXPORT (App → External)
# ============================================================

def from_app_date_to_csv(value: datetime, *, field_name: str) -> str:
    """
    INTENT:
        Convert application datetime to CSV-safe string.

    OUTPUT:
        - 'YYYY-MM-DD'
    """
    assert_app_date(value, field_name=field_name)
    return value.strftime("%Y-%m-%d")


def from_app_date_to_report(value: datetime, *, field_name: str) -> str:
    """
    INTENT:
        Convert application datetime to human-facing string.

    CURRENT FORMAT:
        - 'YYYY-MM-DD'
    """
    assert_app_date(value, field_name=field_name)
    return value.strftime("%Y-%m-%d")


# ============================================================
# SECTION 3 — CORE DATE ASSERTIONS
# ============================================================

def assert_app_date(value: Any, *, field_name: str):
    """
    Assert application-state date integrity.
    """
    if not isinstance(value, datetime):
        raise RuntimeError(
            f"[KERNEL DATE ERROR] Field '{field_name}' must be datetime, "
            f"got {type(value)} with value {value}"
        )


# ============================================================
# SECTION 4 — EVENT ASSERTIONS
# ============================================================

def assert_app_event(event: dict):
    """
    Assert a single event is safe for application execution.
    """
    if not isinstance(event, dict):
        raise RuntimeError(
            f"[KERNEL EVENT ERROR] Event must be dict, got {type(event)}"
        )

    for key in ("tradedate", "tranid"):
        if key not in event:
            raise RuntimeError(
                f"[KERNEL EVENT ERROR] Missing required field '{key}'"
            )

    assert_app_date(event["tradedate"], field_name="event.tradedate")

    if not isinstance(event["tranid"], int):
        raise RuntimeError(
            f"[KERNEL EVENT ERROR] tranid must be int, got {type(event['tranid'])}"
        )


def assert_app_events(events: Iterable[dict], *, context: str):
    """
    Assert a collection of events is kernel-clean.
    """
    if events is None:
        raise RuntimeError(
            f"[KERNEL EVENT SET ERROR] Events is None during {context}. "
            "Ingest must return an iterable (empty list if none)."
        )

    for i, ev in enumerate(events):
        try:
            assert_app_event(ev)
        except Exception as e:
            raise RuntimeError(
                f"[KERNEL EVENT SET ERROR] Invalid event at index {i} during {context}: {e}"
            )


# ============================================================
# SECTION 5 — SCHEDULER ASSERTIONS
# ============================================================

def assert_app_events_ready_for_sort(events: Iterable[dict]):
    """
    Assert events are safe for ordering.
    """
    for ev in events:
        assert_app_date(ev["tradedate"], field_name="event.tradedate")
        if not isinstance(ev["tranid"], int):
            raise RuntimeError(
                f"[KERNEL SORT ERROR] tranid must be int, got {type(ev['tranid'])}"
            )


def assert_app_events_ready_for_processing(events: Iterable[dict]):
    """
    Assert scheduled events are execution-ready.
    """
    for i, ev in enumerate(events):
        if "event_function" not in ev or not callable(ev["event_function"]):
            raise RuntimeError(
                f"[KERNEL PROCESS ERROR] Event {i} missing callable 'event_function'"
            )

        if "args" not in ev or not isinstance(ev["args"], tuple):
            raise RuntimeError(
                f"[KERNEL PROCESS ERROR] Event {i} missing tuple 'args'"
            )

        assert_app_date(ev["tradedate"], field_name="event.tradedate")


# ============================================================
# SECTION 6 — SNAPSHOT ASSERTIONS
# ============================================================

def assert_app_snapshot(snapshot):
    """
    Assert snapshot admissibility.
    """
    if snapshot is None:
        return

    for attr in ("kdbegin", "kdend", "knowledge_date", "kd"):
        if hasattr(snapshot, attr):
            assert_app_date(
                getattr(snapshot, attr),
                field_name=f"snapshot.{attr}"
            )


# ============================================================
# SECTION 7 — GENERIC OBJECT GUARDS
# ============================================================

def assert_app_dates_on_object(obj, *, context: str):
    """
    Assert all '*date*' attributes are datetime.
    """
    for name, value in vars(obj).items():
        if "date" in name.lower():
            assert_app_date(value, field_name=f"{context}.{name}")

def filter_for_knowledge_eligible_events(
    events,
    prior_period_knowledge_cutoff,
    period_cutoff
):
    """
    Return events whose knowledge becomes effective in the current period.

    Canonical rule:
        prior_period_knowledge_cutoff < kdbegin <= period_cutoff

    Notes:
        - Uses kdbegin (NOT knowledge_date)
        - Does NOT use kdend
        - Period cutoff is the hard right boundary
        - Events outside this window must never be processed
    """
    out = []

    for e in events:
        kdbegin = e.get("kdbegin")
        if kdbegin is None:
            continue

        if prior_period_knowledge_cutoff < kdbegin <= period_cutoff:
            out.append(e)

    return out

from pathlib import Path
import json
from datetime import datetime

def select_best_qualifying_snapshot(
    *,
    portfolio,
    calendar,
    knowledge_events,
):
    """
    Select the best qualifying snapshot strictly before the earliest
    economic impact of the provided knowledge-eligible events.

    Returns:
        dict with keys {"kd", "path"} OR
        None  # since inception
    """

    import time
    from pathlib import Path
    from datetime import datetime

    if not knowledge_events:
        raise RuntimeError(
            "[REPLAY ERROR] No knowledge-eligible events supplied"
        )

    # --------------------------------------------------
    # STEP 1: EARLIEST ECONOMIC IMPACT
    # --------------------------------------------------
    t0 = time.perf_counter()
    earliest_trade_date = min(e["tradedate"] for e in knowledge_events)
    print(f"[PROFILE] earliest trade     {time.perf_counter() - t0:8.3f}s")

    # --------------------------------------------------
    # STEP 2: DISCOVER SNAPSHOTS (METADATA ONLY)
    # --------------------------------------------------
    snapshots_dir = (
        Path("C:/Users/hjmne/PycharmProjects/chest/funds")
        / portfolio
        / "Calendars"
        / calendar
        / "Snapshots"
    )

    best_snapshot = None
    best_kd = None

    if snapshots_dir.exists():
        for fn in snapshots_dir.iterdir():
            if fn.suffix != ".pkl":
                continue

            try:
                # Canonical filename: YYYY-MM-DDTHH-MM-SS.pkl
                snapshot_kd = datetime.strptime(
                    fn.stem,
                    "%Y-%m-%dT%H-%M-%S"
                )
            except Exception:
                continue

            # ECONOMIC LAW:
            # snapshot must be strictly before earliest trade
            if snapshot_kd < earliest_trade_date:
                if best_kd is None or snapshot_kd > best_kd:
                    best_kd = snapshot_kd
                    best_snapshot = {
                        "kd": snapshot_kd,
                        "path": fn,
                    }

    print(f"[PROFILE] snapshot scan     {time.perf_counter() - t0:8.3f}s")

    # --------------------------------------------------
    # STEP 3: RETURN SELECTION
    # --------------------------------------------------
    if best_snapshot is not None:
        print(f"[SNAPSHOT] ✅ Using snapshot @ {best_snapshot['kd']}")
        return best_snapshot
    else:
        print("[SNAPSHOT] ❌ No snapshot selected — since inception")
        return None


def load_snapshot_into_space(space, snapshot_path):
    """
    Load snapshot STATE into bookkeeping space.

    CONTRACT (LOCKED):
    ------------------
    snapshot_path:
        - pathlib.Path to snapshot pickle
        - NEVER a dict
        - NEVER contains metadata

    Metadata (kd, period_name, etc.) lives INSIDE the pickle.
    """
    if snapshot_path is None:
        return

    import pickle

    with open(snapshot_path, "rb") as f:
        snapshot = pickle.load(f)

    state = snapshot["state"]

    space.asset_liability_repository = state["asset_liability_repository"]
    space.stat_repo = state["stat_repo"]
    space.admin_facility = state["admin_facility"]
    space.deferred_events = state.get("deferred_events", [])

    # Revenue/Expense: STATE ONLY (no entries)
    space.revenue_expense_repository = state["revenue_expense_repository"]

# ============================================================
# KERNEL UTILITIES — CADENCE MATERIALIZATION
# ============================================================

from datetime import datetime

def materialize_period_outputs(
        *,
        space,
        regular_journals,
        adjusting_journals,
        portfolio: str,
        calendar: str,
        period_name: str,
        snapshot_kd,
        precedence_version: str = None,
        precedence_fingerprint: str = None,
        af=None,
):

    """
    MATERIALIZE PERIOD ARTIFACTS
    - REGULAR journals
    - ADJUSTING journals
    - STATE-ONLY snapshot (NO JEs)
    """

    from datetime import datetime
    from pathlib import Path
    import pickle
    import json
    import psutil
    import os

    # ------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------
    if not isinstance(snapshot_kd, datetime):
        raise RuntimeError("snapshot_kd must be datetime")

    # Normalize snapshot KD to EOD (canonical)
    snapshot_kd = snapshot_kd.replace(
        hour=23, minute=59, second=59, microsecond=999999
    )

    created_at = datetime.utcnow()

    # ------------------------------------------------------------
    # OUTPUT DIRECTORIES
    # ------------------------------------------------------------
    base_dir = (
        Path("C:/Users/hjmne/PycharmProjects/chest/funds")
        / portfolio
        / "Calendars"
        / calendar
    )

    snapshots_dir = base_dir / "Snapshots"
    journals_dir = base_dir / "Journals"

    snapshots_dir.mkdir(parents=True, exist_ok=True)
    journals_dir.mkdir(parents=True, exist_ok=True)

    artifact = snapshot_kd.strftime("%Y-%m-%dT%H-%M-%S")

    # ------------------------------------------------------------
    # WRITE REGULAR JOURNALS (AUTHORITATIVE PASS2 OUTPUT)
    # ------------------------------------------------------------
    with open(journals_dir / f"{artifact}.regular.pkl", "wb") as f:
        pickle.dump(
            {
                "portfolio": portfolio,
                "calendar": calendar,
                "period_name": period_name,
                "snapshot_kd": snapshot_kd,
                "created_at": created_at,
                "precedence_version": precedence_version,  # ← ADD (write 1)
                "precedence_fingerprint": precedence_fingerprint,  # ← ADD
                "journals": list(regular_journals),
            },
            f,
        )

    # ------------------------------------------------------------
    # WRITE ADJUSTING JOURNALS (PASS1 DERIVED, MAY BE EMPTY)
    # ------------------------------------------------------------
    with open(journals_dir / f"{artifact}.adjusting.pkl", "wb") as f:
        pickle.dump(
            {
                "portfolio": portfolio,
                "calendar": calendar,
                "period_name": period_name,
                "snapshot_kd": snapshot_kd,
                "created_at": created_at,
                "precedence_version": precedence_version,  # ← ADD (write 1)
                "precedence_fingerprint": precedence_fingerprint,  # ← ADD
                "journals": list(adjusting_journals or []),
            },
            f,
        )

    # ------------------------------------------------------------
    # WRITE SNAPSHOT (STATE ONLY — NO JOURNALS, NO MUTATION)
    # ------------------------------------------------------------
        # ------------------------------------------------------------
        snapshot = {
            "portfolio": portfolio,
            "calendar": calendar,
            "period_name": period_name,
            "snapshot_kd": snapshot_kd,
            "created_at": created_at,
            "precedence_version": precedence_version,
            "precedence_fingerprint": precedence_fingerprint,
            "state": {
                "asset_liability_repository": space.asset_liability_repository,
                "stat_repo": space.stat_repo,
                "admin_facility": space.admin_facility,
                "revenue_expense_repository": space.revenue_expense_repository,
                "deferred_events": getattr(space, "deferred_events", []),
            },
        }

    re_repo = space.revenue_expense_repository

    xom_space = re_repo.balance_spaces_library.get("XOM")

    print(xom_space is None)
    print(xom_space.keys() if xom_space else None)
    if xom_space:
        for k, v in xom_space["entries"].items():
            if k[6] == "PriceGainInvestment":
                print(k, v)

    snapshot_path = snapshots_dir / f"{artifact}.pkl"
    meta_path = snapshots_dir / f"{artifact}.json"

    with open(snapshot_path, "wb") as f:
        pickle.dump(snapshot, f)

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "portfolio": portfolio,
                "calendar": calendar,
                "period_name": period_name,
                "snapshot_kd": snapshot_kd.isoformat(),
                "created_at": created_at.isoformat(),
            },
            f,
            indent=2,
        )
    # ------------------------------------------------------------
    # MEMORY TRACE (SAFE)
    # ------------------------------------------------------------
    process = psutil.Process(os.getpid())
    rss_mb = process.memory_info().rss / 1024 / 1024
    print(f"[MEMORY] RSS after period close: {rss_mb:.2f} MB")


# ======================================================================
# CLOSE PERIOD
# ======================================================================

from datetime import datetime, timedelta
import json
import copy


def close_and_create_new_period(fund, calendar, period_name):

    cal_file = (
        f"C:/Users/hjmne/PycharmProjects/chest/funds/"
        f"{fund}/Calendars/{calendar}/{calendar}.txt"
    )

    # --------------------------------------------------
    # Load calendar records
    # --------------------------------------------------
    with open(cal_file, "r") as f:
        records = [
            json.loads(ln.strip())
            for ln in f
            if ln.strip().startswith("{")
        ]

    idx = next(
        i for i, r in enumerate(records)
        if r["period_name"] == period_name
    )

    rec = records[idx]

    # --------------------------------------------------
    # Close current period
    # --------------------------------------------------
    from datetime import datetime, timedelta
    from dateutil.relativedelta import relativedelta

    # Close current period
    rec["period_status"] = "Closed"

    cutoff_dt = datetime.strptime(
        rec["current_period_cutoff"], "%Y-%m-%d:%H:%M:%S"
    )

    # Next period starts immediately after prior cutoff
    new_start_dt = cutoff_dt + timedelta(seconds=1)
    new_start = new_start_dt.strftime("%Y-%m-%d:%H:%M:%S")

    # Next period ends one calendar month after prior cutoff
    new_end_dt = cutoff_dt + relativedelta(months=1)
    new_end = new_end_dt.strftime("%Y-%m-%d:%H:%M:%S")

    # --------------------------------------------------
    # Create NEXT period (PENDING)
    # --------------------------------------------------
    new_period = copy.deepcopy(rec)

    new_period["period_name"] = new_start_dt.strftime("%Y-%m")
    new_period["period_status"] = "Pending"

    new_period["prior_period_start"] = rec["current_period_start"]
    new_period["prior_period_cutoff"] = rec["current_period_cutoff"]
    new_period["prior_period_knowledge"] = rec["current_period_knowledge"]

    new_period["current_period_start"] = new_start
    new_period["current_period_cutoff"] = new_end
    new_period["current_period_knowledge"] = ""

    # --------------------------------------------------
    # Insert + persist
    # --------------------------------------------------
    records.insert(idx + 1, new_period)

    with open(cal_file, "w") as f:
        f.write("Calendar Records\n")
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(
        f"✔ Closed period '{period_name}' "
        f"and created pending → {new_period['period_name']}"
    )

def update_period_end_knowledge(fund, calendar, period_name, current_period_knowledge):
    """
    AUTHORITATIVE UPDATE:
    ---------------------zzz
    Update current_period_knowledge for an existing calendar period.

    RULES:
    - Must be called ONLY after successful CPH execution
    - Does NOT change period status
    - Does NOT create new periods
    - current_period_knowledge must be datetime.datetime
    """

    import json
    from datetime import datetime

    # ------------------------------------------------------------
    # Assertions (kernel discipline)
    # ------------------------------------------------------------
    if not isinstance(current_period_knowledge, datetime):
        raise RuntimeError(
            f"[CALENDAR ERROR] current_period_knowledge must be datetime, got {type(current_period_knowledge)}"
        )

    cal_file = (
        f"C:/Users/hjmne/PycharmProjects/chest/funds/"
        f"{fund}/Calendars/{calendar}/{calendar}.txt"
    )

    # ------------------------------------------------------------
    # Load calendar records
    # ------------------------------------------------------------
    with open(cal_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    header = None  # Calendar files do NOT require a header
    records = [
        json.loads(ln.strip())
        for ln in lines
        if ln.strip().startswith("{")
    ]

    # ------------------------------------------------------------
    # Locate target period
    # ------------------------------------------------------------
    rec = next(
        (r for r in records if r.get("period_name") == period_name),
        None
    )

    if rec is None:
        raise RuntimeError(
            f"[CALENDAR ERROR] Period '{period_name}' not found in calendar '{calendar}'"
        )

    # ------------------------------------------------------------
    # Update knowledge boundary
    # ------------------------------------------------------------
    rec["current_period_knowledge"] = current_period_knowledge.strftime(
        "%Y-%m-%d:%H:%M:%S"
    )

    # ------------------------------------------------------------
    # Persist calendar file (atomic rewrite)
    # ------------------------------------------------------------
    with open(cal_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(
        f"✔ Updated period knowledge → "
        f"{period_name} = {rec['current_period_knowledge']}"
    )

# ============================================================
# 🔹 BOOTSTRAP INVESTMENT ATTRIBUTES
# ============================================================

def bootstrap_investment_attributes(space, portfolio: str):
    """
    Bootstrap structural investment attributes (AIFs)
    from portfolio RefData files into live BookkeepingSpace.

    This must ONLY be called when:
      - No snapshot exists
      - We are initializing portfolio from zero state

    After first snapshot, attributes must come from snapshot.
    """

    import os
    import csv

    base_path = "C:/Users/hjmne/PycharmProjects/chest"

    investment_master_path = (
        f"{base_path}/funds/{portfolio}/RefData/investment_master.csv"
    )

    bond_info_path = (
        f"{base_path}/funds/{portfolio}/RefData/bond_info.csv"
    )

    repo = space.asset_liability_repository

    # ------------------------------------------------------------
    # LOAD INVESTMENT MASTER
    # ------------------------------------------------------------
    if os.path.exists(investment_master_path):

        with open(investment_master_path, newline="") as f:
            rows = list(csv.DictReader(f))

        for r in rows:
            investment = r.get("investment")
            if not investment:
                continue

            for field, value in r.items():
                if field == "investment":
                    continue
                if value in ("", None):
                    continue

                if field not in repo.allowed_aifs:
                    continue

                space.set_investment_attribute(
                    investment=investment,
                    field_type="AIF",
                    attribute=field,
                    value=value,
                )

    # ------------------------------------------------------------
    # LOAD BOND INFO (EXTENDS ATTRIBUTES)
    # ------------------------------------------------------------
    if os.path.exists(bond_info_path):

        with open(bond_info_path, newline="") as f:
            rows = list(csv.DictReader(f))

        for r in rows:
            investment = r.get("investment")
            if not investment:
                continue

            for field, value in r.items():
                if field == "investment":
                    continue
                if value in ("", None):
                    continue

                if field not in repo.allowed_aifs:
                    continue

                space.set_investment_attribute(
                    investment=investment,
                    field_type="AIF",
                    attribute=field,
                    value=value,
                )

    print("✅ Bootstrap investment attributes complete")
