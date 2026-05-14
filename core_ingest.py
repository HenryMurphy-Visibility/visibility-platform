import time
from contextlib import contextmanager

@contextmanager
def _t(label):
    t0 = time.perf_counter()
    yield
    dt = time.perf_counter() - t0
    print(f"[TIMER] {label:<45} {dt:9.4f}s")


print("IMPORTING core_ingest")

# ============================================================
# CORE INGESTION (AUTHORITATIVE ORCHESTRATOR)
# ============================================================

from typing import List, Dict, Tuple
import os
from datetime import datetime

PRICE_MASTER_PATH = (
    "C:/Users/hjmne/PycharmProjects/chest/refdata/price_master.csv"
)

FX_MASTER_PATH = (
    "C:/Users/hjmne/PycharmProjects/chest/refdata/fx_master.csv"
)

BASE_PATH = "C:/users/hjmne/pycharmprojects/chest"


from datetime import datetime

# ----------------------------------------------------------------------
# INGEST CONTEXT BUILDER (NO EVENT LOGIC)
# ----------------------------------------------------------------------

def build_interpretation_ctx(
    *,
    portfolio,
    calendar,
    period_name,
    space,
    all_events,
):
    """
    Determine replay start and snapshot usage for a single period.

    Rules:
    - Only events with NEW KNOWLEDGE in this period are considered
    - Earliest impacted TRADE DATE defines economic rewind
    - Snapshot must have snapshot_kd STRICTLY BEFORE that trade date
    - Snapshot discovery is disk-based, no index, no cache
    """

    from pathlib import Path
    from datetime import datetime
    import pickle
    import time
    from kernel_utilities import from_csv_date_to_app

    t0_total = time.perf_counter()
    print("[INTERPRET] start")

    # --------------------------------------------------
    # LOAD CALENDAR
    # --------------------------------------------------
    t0 = time.perf_counter()
    (
        current_period_start,
        current_period_cutoff,
        current_period_knowledge,
        prior_period_start,
        prior_period_cutoff,
        prior_period_knowledge,
        calendar_index,
    ) = load_calendar(portfolio, calendar, period_name)
    print(f"[PROFILE] calendar load      {time.perf_counter() - t0:8.3f}s")

    ctx = IngestContext(
        calendar=calendar,
        period_name=period_name,
        current_period_start=current_period_start,
        current_period_cutoff=current_period_cutoff,
        current_period_knowledge=current_period_knowledge,
        prior_period_start=prior_period_start,
        prior_period_cutoff=prior_period_cutoff,
        prior_period_knowledge=prior_period_knowledge,
        calendar_index=calendar_index,
        all_events=all_events,
    )

    # --------------------------------------------------
    # STEP 1: EVENTS WITH NEW KNOWLEDGE
    # --------------------------------------------------
    t0 = time.perf_counter()
    knowledge_events = [
        e for e in all_events
        if prior_period_knowledge < e["kdbegin"] <= current_period_knowledge
    ]
    print(f"[PROFILE] knowledge filter   {time.perf_counter() - t0:8.3f}s")

    if not knowledge_events:
        raise RuntimeError(
            f"[REPLAY ERROR] No knowledge-eligible events for period {period_name}"
        )

    # --------------------------------------------------
    # STEP 2: EARLIEST ECONOMIC IMPACT
    # --------------------------------------------------
    t0 = time.perf_counter()
    earliest_trade_date = min(e["tradedate"] for e in knowledge_events)
    print(f"[PROFILE] earliest trade     {time.perf_counter() - t0:8.3f}s")

    # --------------------------------------------------
    # STEP 3: DISCOVER SNAPSHOTS (DISK-BASED, METADATA ONLY)
    # --------------------------------------------------
    from datetime import datetime

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
                # Snapshot filenames are canonical:
                # YYYY-MM-DDTHH-MM-SS.pkl
                snapshot_kd = datetime.strptime(
                    fn.stem,
                    "%Y-%m-%dT%H-%M-%S"
                )
            except Exception:
                continue

            # ECONOMIC LAW: snapshot must be strictly before earliest trade
            if snapshot_kd < earliest_trade_date:
                if best_kd is None or snapshot_kd > best_kd:
                    best_kd = snapshot_kd
                    best_snapshot = {
                        "kd": snapshot_kd,
                        "path": fn,
                    }

    print(f"[PROFILE] snapshot scan     {time.perf_counter() - t0:8.3f}s")

    # --------------------------------------------------
    # STEP 4: REPLAY START
    # --------------------------------------------------
    if best_snapshot is not None:
        ctx.selected_snapshot = best_snapshot
        ctx.replay_start = best_snapshot["kd"]
        print(f"[SNAPSHOT] ✅ Using snapshot @ {best_snapshot['kd']}")
    else:
        ctx.selected_snapshot = None
        ctx.replay_start = earliest_trade_date
        print("[SNAPSHOT] ❌ No snapshot selected — cold replay")

    print(f"[TIME] interpretation.TOTAL {time.perf_counter() - t0_total:8.3f}s")

    return ctx

class IngestContext:
    def __init__(
        self,
        calendar,
        period_name,
        current_period_start,
        current_period_cutoff,
        current_period_knowledge,
        prior_period_start,
        prior_period_cutoff,
        prior_period_knowledge,
        calendar_index,
        all_events,
    ):
        # --------------------------------------------------
        # Runtime calendar / period selection
        # --------------------------------------------------
        self.calendar = calendar
        self.period_name = period_name

        self.current_period_start = current_period_start
        self.current_period_cutoff = current_period_cutoff
        self.current_period_knowledge = current_period_knowledge

        self.prior_period_start = prior_period_start
        self.prior_period_cutoff = prior_period_cutoff
        self.prior_period_knowledge = prior_period_knowledge

        # --------------------------------------------------
        # REQUIRED FLAGS
        # --------------------------------------------------
        self.calendar_index = calendar_index
        self.has_prior_period = calendar_index > 0

        # --------------------------------------------------
        # Replay control (resolved in CPH)
        # --------------------------------------------------
        self.selected_snapshot = None
        self.replay_start = None

        # System fallback
        self.default_inception = datetime(2021, 1, 3, 0, 0, 0)

        # --------------------------------------------------
        # Ingest metrics
        # --------------------------------------------------
        self.total_regular_events = 0
        self.unapplied_regular_events = 0
        self.total_mark_events = 0
        self.mark_and_unapplied_regular_events = 0
        self.total_aif_events = 0

        # --------------------------------------------------
        # Event universe (PRELOADED AT TOP LEVEL)
        # --------------------------------------------------
        self.all_events = all_events

        # --------------------------------------------------
        # State
        # --------------------------------------------------
        self.no_new_events_detected = False
        self.message = None
        self.global_refdata = None

# ============================================================
# VALIDATION
# ============================================================
def validate_calendar_context(ctx: IngestContext):


    if ctx.current_period_start >= ctx.current_period_cutoff:
        raise RuntimeError("Invalid calendar: current_period_start >= current_period_cutoff")

def load_calendar(fund: str, calendar: str, period_name: str):
    """
    LOAD_CALENDAR (UI-SAFE)

    Reads calendar file, selects the requested period record,
    and returns normalized datetime boundaries.

    RETURN CONTRACT:
        (
            current_period_start,
            current_period_cutoff,
            current_period_knowledge,
            prior_period_knowledge,
            prior_period_cutoff,
            calendar_index,
        )
    OR (None, None, None, None, None, None) on soft failure
    """

    import json
    from kernel_utilities import kernel_guard, from_csv_date_to_app

    if not period_name:
        period_name = "Base Period"

    # ------------------------------------------------------------
    # LOAD + PARSE CALENDAR FILE
    # ------------------------------------------------------------
    with kernel_guard("LOAD_CALENDAR: FILE READ + PARSE"):
        cal_path = (
            f"C:/Users/hjmne/PycharmProjects/chest/funds/"
            f"{fund}/Calendars/{calendar}/{calendar}.txt"
        )

        records = []

        try:
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
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            print(f"[CALENDAR WARNING] File not found: {cal_path}")
            return None, None, None, None, None, None, None

        if not records:
            print(f"[CALENDAR WARNING] No valid records in {cal_path}")
            return None, None, None, None, None, None, None

        try:
            sel_idx = next(
                i for i, r in enumerate(records)
                if r.get("period_name") == period_name
            )
        except StopIteration:
            print(
                f"[CALENDAR WARNING] Period '{period_name}' not found "
                f"in calendar '{calendar}'"
            )
            return None, None, None, None, None, None, None

        sel = records[sel_idx]

    # ------------------------------------------------------------
    # DATE NORMALIZATION
    # ------------------------------------------------------------
    with kernel_guard("LOAD_CALENDAR: DATE NORMALIZATION"):
        try:
            current_period_start = from_csv_date_to_app(
                sel["current_period_start"],
                field_name="current_period_start"
            )

            current_period_cutoff = from_csv_date_to_app(
                sel["current_period_cutoff"],
                field_name="current_period_cutoff"
            )

            current_period_knowledge = from_csv_date_to_app(
                sel["current_period_knowledge"],
                field_name="current_period_knowledge"
            )


            prior_period_start = from_csv_date_to_app(
                sel["prior_period_start"],
                field_name="prior_period_start"
            )

            prior_period_cutoff = from_csv_date_to_app(
                sel["prior_period_cutoff"],
                field_name="prior_period_cutoff"
            )

            prior_period_knowledge = from_csv_date_to_app(
                sel["prior_period_knowledge"],
                field_name="prior_period_knowledge"
            )

        except Exception as e:
            print(f"[CALENDAR WARNING] Date normalization failed: {e}")
            return None, None, None, None, None, None

    # ------------------------------------------------------------
    # RETURN (AUTHORITATIVE)
    # ------------------------------------------------------------
    return (
        current_period_start,
        current_period_cutoff,
        current_period_knowledge,
        prior_period_start,
        prior_period_cutoff,
        prior_period_knowledge,
        sel_idx,
    )


def discover_snapshot_candidates(snap_root, earliest_kd):
    """
    Discover snapshot candidates across ALL prior periods.
    Returns metadata only. NO state loading.
    """
    from pathlib import Path
    import pickle
    from datetime import datetime
    from kernel_utilities import from_csv_date_to_app

    snapshots = []

    if not snap_root.exists():
        return snapshots

    # Walk ALL period directories
    for period_dir in snap_root.iterdir():
        if not period_dir.is_dir():
            continue

        snap_dir = period_dir / "Outputs" / "Snapshots"
        if not snap_dir.exists():
            continue

        for fn in snap_dir.iterdir():
            if fn.suffix != ".pkl":
                continue

            try:
                with open(fn, "rb") as f:
                    snap = pickle.load(f)
            except Exception:
                continue

            if not isinstance(snap, dict):
                continue

            if "snapshot_kd" not in snap:
                continue

            raw_kd = snap["snapshot_kd"]
            snapshot_kd = (
                raw_kd
                if isinstance(raw_kd, datetime)
                else from_csv_date_to_app(raw_kd, field_name="snapshot_kd")
            )

            # 🔒 ECONOMIC VIOLATION GUARD
            if snapshot_kd > earliest_kd:
                continue

            snapshots.append({
                "kd": snapshot_kd,
                "path": fn,
            })

    return snapshots

def remove_violated_snapshots(
    snapshots,
    earliest_trade_date,
):
    """
    Remove snapshots invalidated by economic truth.

    A snapshot is violated if:
        snapshot.kd >= earliest_trade_date
    """

    valid = []

    for snap in snapshots:
        kd = snap.get("kd")
        if kd is None:
            continue

        if kd < earliest_trade_date:
            valid.append(snap)

    return valid


# ============================================================
# CANDIDATE DERIVATION
# ============================================================

def derive_candidates_from_events(events: List[Dict]) -> Dict[Tuple[str, str], datetime]:
    candidates = {}

    for e in events:
        key = (e["portfolio"], e["investment"])
        td = e["tradedate"]

        if key not in candidates or td < candidates[key]:
            candidates[key] = td

    return candidates

def select_best_snapshot(candidates):
    """
    Select the single best snapshot (latest kd).
    """
    if not candidates:
        return None
    return max(candidates, key=lambda s: s["kd"])

def load_snapshot_state(snapshot_path):
    """
    Load sealed bookkeeping state from snapshot.
    """
    import pickle

    with open(snapshot_path, "rb") as f:
        snap = pickle.load(f)

    if not isinstance(snap, dict):
        raise RuntimeError("Snapshot file is not a dict")

    if "state" not in snap:
        raise RuntimeError("Snapshot missing 'state' block")

    return snap["state"]
