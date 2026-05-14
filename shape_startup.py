# ============================================================
# shape_startup.py
# ============================================================

from pathlib import Path
import pickle
from datetime import datetime
from collections import defaultdict
from typing import Dict, Any

from bookkeeping import BookkeepingSpace
from kernel_utilities import load_snapshot_into_space
from shape_extraction import extract_structural_state_from_space


TOLERANCE = 0.0001


# ============================================================
# LOAD SNAPSHOT INTO SPACE
# ============================================================

def passes_filter(obj, filter_dict):
    """
    obj: either structural row (dict) or JournalEntry
    filter_dict: {"dimension": value or list}
    """

    if not filter_dict:
        return True

    for dim, val in filter_dict.items():

        # normalize to list
        if not isinstance(val, (list, tuple, set)):
            val = [val]

        # support dict row or JE object
        if isinstance(obj, dict):
            field_value = obj.get(dim)
        else:
            field_value = getattr(obj, dim, None)

        if field_value not in val:
            return False

    return True

def load_space(snapshot_path: Path) -> BookkeepingSpace:
    space = BookkeepingSpace()
    load_snapshot_into_space(space, snapshot_path)
    return space

def build_period_snapshot_map(snapshots_dir: Path):
    """
    Returns:
        {
            "2021-01": Path(...2021-01-31T23-59-59.pkl),
            "2021-02": Path(...2021-02-28T23-59-59.pkl),
        }
    """

    period_map = {}

    for snap in snapshots_dir.glob("*.pkl"):

        with open(snap, "rb") as f:
            container = pickle.load(f)

        period_name = container.get("period_name")

        if not period_name:
            continue

        period_map[period_name] = snap

    return dict(sorted(period_map.items()))

def load_period_journals(
    space,
    journals_dir: Path,
    snapshot_path: Path,
    portfolio: str,
):
    """
    Given snapshot path, automatically fetch:
        - .regular.pkl
        - .adjusting.pkl
    """

    period_stub = snapshot_path.stem  # ISO timestamp

    regular_file = journals_dir / f"{period_stub}.regular.pkl"
    adjusting_file = journals_dir / f"{period_stub}.adjusting.pkl"

    regular = space.load_journals(regular_file, portfolio)
    adjusting = space.load_journals(adjusting_file, portfolio)

    return regular + adjusting

# ============================================================
# BUILD FULL PERIOD BALANCE VIEW
# ============================================================

EXCLUDED_FA = {"UnrealPriceGLOffset"}
#EXCLUDED_FA = {"MarketVal", "UnrealPriceGLOffset"}

from typing import Optional, Dict, Any
uber_filter = None
def build_period_balances(
    prior_structural: Dict[tuple, Dict[str, Any]],
    current_structural: Dict[tuple, Dict[str, Any]],
    journal_entries: list,
    prior_kd: datetime,
    current_kd: datetime,
    uber_filter: Optional[Dict[str, Any]] = None,
):

    balances = defaultdict(lambda: {
        "opening_qty": 0.0,
        "opening_local": 0.0,
        "opening_book": 0.0,
        "movement_qty": 0.0,
        "movement_local": 0.0,
        "movement_book": 0.0,
        "closing_qty": 0.0,
        "closing_local": 0.0,
        "closing_book": 0.0,
        "je_lines": []
    })

    # ------------------------------------------------------------
    # OPENING
    # ------------------------------------------------------------

    for row in prior_structural.values():

        fa = row["financial_account"]
        if fa in EXCLUDED_FA:
            continue

        if not passes_filter(row, uber_filter):
            continue

        key = (
            row["investment"],
            row["location"],
            row["ls"],
            fa,
        )

        bal = balances[key]
        bal["opening_qty"] += row.get("quantity") or 0.0
        bal["opening_local"] += row.get("local") or 0.0
        bal["opening_book"] += row.get("book") or 0.0

    # ------------------------------------------------------------
    # MOVEMENT + JE DETAIL
    # ------------------------------------------------------------

    for je in journal_entries:

        if je.financial_account in EXCLUDED_FA:
            continue

        if not (prior_kd < je.ibor_date <= current_kd):
            continue

        if not passes_filter(je, uber_filter):
            continue

        qty = je.quantity or 0.0
        local = je.local or 0.0
        book = je.book or 0.0

        # Skip zero-impact JE lines
        if abs(qty) < 0.0001 and abs(local) < 0.0001 and abs(book) < 0.0001:
            continue

        key = (
            je.investment,
            je.location,
            je.ls,
            je.financial_account,
        )

        bal = balances[key]

        bal["movement_qty"] += qty
        bal["movement_local"] += local
        bal["movement_book"] += book

        bal["je_lines"].append({
            "date": je.ibor_date,
            "sequence": je.sequence_number,
            "transaction": je.transaction,
            "tranid": je.tranid,
            "lotid": je.lotid,
            "tax_date": je.tax_date,
            "financial_account": je.financial_account,
            "qty": qty,
            "local": local,
            "book": book,
        })

    # ------------------------------------------------------------
    # CLOSING
    # ------------------------------------------------------------

    for row in current_structural.values():

        fa = row["financial_account"]
        if fa in EXCLUDED_FA:
            continue

        if not passes_filter(row, uber_filter):
            continue

        key = (
            row["investment"],
            row["location"],
            row["ls"],
            fa,
        )

        bal = balances[key]
        bal["closing_qty"] += row.get("quantity") or 0.0
        bal["closing_local"] += row.get("local") or 0.0
        bal["closing_book"] += row.get("book") or 0.0

# ============================================================
# MAIN
# ============================================================

def main():

    from pathlib import Path
    import pickle
    from datetime import datetime



    # ------------------------------------------------------------
    # USER INPUT — PERIOD NAMES ONLY
    # ------------------------------------------------------------
    portfolio = "Portfolio1"
    calendar = "Monthly"
    period_start = "2025-01"
    period_end   = "2025-12"   # same = single box view

    # Optional Uber Filter
    filter_dimension = "tranid"
    filter_value = 76257

    # ------------------------------------------------------------
    # BUILD UBER FILTER
    # ------------------------------------------------------------

    if filter_dimension:
        uber_filter = {filter_dimension: filter_value}
    else:
        uber_filter = None

    # ------------------------------------------------------------
    # DIRECTORIES
    # ------------------------------------------------------------

    base_dir = (
        Path("C:/Users/hjmne/PycharmProjects/chest/funds")
        / portfolio
        / "Calendars"
        / calendar
    )

    snapshots_dir = base_dir / "Snapshots"
    journals_dir  = base_dir / "Journals"

    # ------------------------------------------------------------
    # BUILD PERIOD → SNAPSHOT MAP
    # ------------------------------------------------------------

    period_map = {}

    for snap in snapshots_dir.glob("*.pkl"):

        with open(snap, "rb") as f:
            container = pickle.load(f)

        period_name = container.get("period_name")

        if period_name:
            period_map[period_name] = snap

    if not period_map:
        raise RuntimeError("No snapshots found.")

    # sort by period name
    period_names = sorted(period_map.keys())

    if period_start not in period_map:
        raise RuntimeError(f"Unknown period_start: {period_start}")

    if period_end not in period_map:
        raise RuntimeError(f"Unknown period_end: {period_end}")

    start_index = period_names.index(period_start)
    end_index   = period_names.index(period_end)

    if end_index < start_index:
        raise RuntimeError("period_end must be >= period_start")

    # ------------------------------------------------------------
    # OPENING SNAPSHOT (PRECEDING BOX)
    # ------------------------------------------------------------

    if start_index == 0:
        print("⚠ First box selected — opening balances assumed zero.")
        prior_structural = {}
        prior_kd = datetime.min
    else:
        opening_snapshot = period_map[period_names[start_index - 1]]

        print("\nOPENING SNAPSHOT:", opening_snapshot.name)

        prior_space = load_space(opening_snapshot)

        with open(opening_snapshot, "rb") as f:
            prior_kd = pickle.load(f)["snapshot_kd"]

        prior_structural = extract_structural_state_from_space(prior_space,  )

    # ------------------------------------------------------------
    # CLOSING SNAPSHOT
    # ------------------------------------------------------------

    closing_snapshot = period_map[period_end]

    print("CLOSING SNAPSHOT:", closing_snapshot.name)

    current_space = load_space(closing_snapshot)

    with open(closing_snapshot, "rb") as f:
        current_kd = pickle.load(f)["snapshot_kd"]

    current_structural = extract_structural_state_from_space(current_space)

    # ------------------------------------------------------------
    # LOAD JOURNALS FOR RANGE
    # ------------------------------------------------------------

    period_journals = []

    for i in range(start_index, end_index + 1):

        snap = period_map[period_names[i]]
        period_stub = snap.stem

        regular_file   = journals_dir / f"{period_stub}.regular.pkl"
        adjusting_file = journals_dir / f"{period_stub}.adjusting.pkl"

        print(f"Loading journals for period {period_names[i]}")

        regular   = current_space.load_journals(regular_file, portfolio)
        adjusting = current_space.load_journals(adjusting_file, portfolio)

        period_journals.extend(regular)
        period_journals.extend(adjusting)

    print(f"Total JEs loaded: {len(period_journals)}")

    # ------------------------------------------------------------
    # BUILD PERIOD BALANCE VIEW
    # ------------------------------------------------------------

    build_period_balances(
        prior_structural,
        current_structural,
        period_journals,
        prior_kd,
        current_kd,
        uber_filter,
    )

if __name__ == "__main__":
    main()
