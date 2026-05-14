# financial_information_gateway/extraction/box_extractor.py

from pathlib import Path
import pickle
from datetime import datetime
from bookkeeping import BookkeepingSpace
from kernel_utilities import load_snapshot_into_space
from shape_extraction import extract_structural_state_from_space


def load_space(snapshot_path: Path) -> BookkeepingSpace:
    space = BookkeepingSpace()
    load_snapshot_into_space(space, snapshot_path)
    return space


def extract_box_components(
        portfolio: str,
        calendar: str,
        period_start: str,
        period_end: str,
        uber_filter=None,

):
    base_dir = (
            Path("C:/Users/hjmne/PycharmProjects/chest/funds")
            / portfolio
            / "Calendars"
            / calendar
    )

    snapshots_dir = base_dir / "Snapshots"
    journals_dir = base_dir / "Journals"

    period_map = {}

    # ------------------------------------------------------------
    # BUILD PERIOD MAP
    # ------------------------------------------------------------

    for snap in snapshots_dir.glob("*.pkl"):
        base_date_str = snap.stem.split("T")[0]
        period_name = derive_calendar_identity(base_date_str, calendar)

        period_map[period_name] = snap

    if not period_map:
        raise RuntimeError("No snapshots found.")

    period_names = sorted(period_map.keys())

    if period_start not in period_map:
        raise RuntimeError(f"Unknown period_start: {period_start}")

    if period_end not in period_map:
        raise RuntimeError(f"Unknown period_end: {period_end}")

    start_index = period_names.index(period_start)
    end_index = period_names.index(period_end)

    if end_index < start_index:
        raise RuntimeError("period_end must be >= period_start")

    # ------------------------------------------------------------
    # PRIOR SNAPSHOT
    # ------------------------------------------------------------

    if start_index == 0:

        prior_structural = {}
        prior_kd = datetime.min

    else:

        opening_snapshot = period_map[period_names[start_index - 1]]

        with open(opening_snapshot, "rb") as f:
            snapshot = pickle.load(f)

        prior_kd = snapshot["snapshot_kd"]

        prior_space = load_space(opening_snapshot)

        # critical: structural extraction must see ALL repositories
        prior_structural = extract_structural_state_from_space(prior_space)

    # ------------------------------------------------------------
    # CURRENT SNAPSHOT
    # ------------------------------------------------------------

    closing_snapshot = period_map[period_end]

    with open(closing_snapshot, "rb") as f:
        snapshot = pickle.load(f)

    current_kd = snapshot["snapshot_kd"]

    current_space = load_space(closing_snapshot)

    # critical: structural extraction must see ALL repositories
    current_structural = extract_structural_state_from_space(current_space)

    # ------------------------------------------------------------
    # LOAD SPACE (FOR JOURNAL REPLAY)
    # ------------------------------------------------------------

    space = load_space(closing_snapshot)

    # ------------------------------------------------------------
    # LOAD JOURNALS
    # ------------------------------------------------------------

    period_journals = []

    for i in range(start_index, end_index + 1):

        snap = period_map[period_names[i]]
        period_stub = snap.stem

        regular_file = journals_dir / f"{period_stub}.regular.pkl"
        adjusting_file = journals_dir / f"{period_stub}.adjusting.pkl"

        if regular_file.exists():
            regular = space.load_journals(regular_file, portfolio)
            period_journals.extend(regular)

        if adjusting_file.exists():
            adjusting = space.load_journals(adjusting_file, portfolio)
            period_journals.extend(adjusting)

    # ------------------------------------------------------------
    # RETURN COMPONENTS
    # ------------------------------------------------------------

    return {
        "prior_structural": prior_structural,
        "current_structural": current_structural,
        "journal_entries": period_journals,
        "prior_kd": prior_kd,
        "current_kd": current_kd,
        "uber_filter": uber_filter,
    }

def derive_calendar_identity(base_date_str: str, calendar: str) -> str:
    dt = datetime.strptime(base_date_str, "%Y-%m-%d")

    if calendar == "Yearly":
        return f"{dt.year}"

    if calendar == "Quarterly":
        quarter = (dt.month - 1) // 3 + 1
        return f"{dt.year}-Q{quarter}"

    if calendar == "Monthly":
        return f"{dt.year}-{dt.month:02d}"

    if calendar == "Daily":
        return dt.strftime("%Y-%m-%d")

    if calendar == "Operational":
        return f"{dt.year}-{dt.month:02d}"

    raise ValueError(f"Unsupported calendar: {calendar}")