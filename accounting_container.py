# chest/funds/{portfolio}/{calendar}/Periods/{period_name}/
# │
# ├── Inputs/
# │   ├── RegularEvents/
# │   ├── InvestmentEvents/
# │   ├── InvestmentEventMethods/
# │   └── MarkEvents/
# │
# └── Outputs/
#     ├── Journals/
#     │   ├── journals.pkl
#     │   └── adjusting_journals.pkl
#     │
#     ├── Statistics/
#     │   └── stat_repo.pkl
#     │
#     ├── Chores/
#     │   └── settlement_admin_facility.pkl
#     │
#     └── Snapshots/
#         └── snapshot_{period_name}.pkl
# ======================================================================
#  accounting_container.py
# ======================================================================
"""
ACCOUNTING CONTAINER

Purpose
-------
An AccountingContainer represents a single sealed accounting period.

It owns:
- All OUTPUTS produced by execution (CPH)
- Zero execution logic
- Zero inference
- Zero mutation after sealing

Design Guarantees
-----------------
- Containers are immutable once sealed
- Containers are filesystem-addressable
- Containers can be hydrated deterministically
- Containers can be safely reassembled
- Containers survive interruption (pull-the-plug safe)

This is the atomic unit of historical accounting truth.
"""

from pathlib import Path
import pickle
from dataclasses import dataclass
from typing import Optional


# ======================================================================
#  AccountingContainer
# ======================================================================
@dataclass
class AccountingContainer:
    portfolio: str
    calendar: str
    period_name: str

    # ------------------------------------------------------------------
    # Path construction (LOCKED CONTRACT)
    # ------------------------------------------------------------------
    def __post_init__(self):
        self.base_path = (
            Path("C:/Users/hjmne/PycharmProjects/chest/funds")
            / self.portfolio
            / self.calendar
            / "Periods"
            / self.period_name
        )

        self.inputs_path = self.base_path / "Inputs"
        self.outputs_path = self.base_path / "Outputs"

        self.journals_path = self.outputs_path / "Journals"
        self.statistics_path = self.outputs_path / "Statistics"
        self.admin_facility_path = self.outputs_path / "Chores"
        self.snapshots_path = self.outputs_path / "Snapshots"

    # ------------------------------------------------------------------
    # Filesystem bootstrap
    # ------------------------------------------------------------------
    def ensure_structure(self):
        """
        Create required directory structure if missing.
        Safe to call repeatedly.
        """
        for p in [
            self.inputs_path / "RegularEvents",
            self.inputs_path / "InvestmentEvents",
            self.inputs_path / "InvestmentEventMethods",
            self.inputs_path / "MarkEvents",
            self.journals_path,
            self.statistics_path,
            self.admin_facility_path,
            self.snapshots_path,
        ]:
            p.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Seal outputs (WRITE ONCE)
    # ------------------------------------------------------------------
    def seal_outputs(
        self,
        *,
        journals,
        stat_repo,
        settlement_admin_facility,
        snapshot: Optional[dict] = None,
        adjusting_journals: Optional[list] = None,
    ):
        """
        Persist all execution outputs for this period.

        This method:
        - Writes all artifacts atomically
        - Overwrites nothing implicitly
        - Is safe to rerun intentionally
        """

        self.ensure_structure()

        # ---------------- Journals ----------------
        journals_file = self.journals_path / "journals.pkl"
        with journals_file.open("wb") as f:
            pickle.dump(journals, f)

        if adjusting_journals is not None:
            adj_file = self.journals_path / "adjusting_journals.pkl"
            with adj_file.open("wb") as f:
                pickle.dump(adjusting_journals, f)

        # ---------------- Statistics ----------------
        stat_file = self.statistics_path / "stat_repo.pkl"
        with stat_file.open("wb") as f:
            pickle.dump(stat_repo, f)

        # ---------------- Settlement Chores ----------------
        admin_facility_file = self.admin_facility_path / "settlement_admin_facility.pkl"
        with admin_facility_file.open("wb") as f:
            pickle.dump(settlement_admin_facility, f)

        # ---------------- Snapshot ----------------
        if snapshot is not None:
            snap_file = (
                self.snapshots_path
                / f"snapshot_{self.period_name}.pkl"
            )
            with snap_file.open("wb") as f:
                pickle.dump(snapshot, f)

    # ------------------------------------------------------------------
    # Hydration (READ ONLY)
    # ------------------------------------------------------------------
    def hydrate_journals(self):
        journals_file = self.journals_path / "journals.pkl"
        if not journals_file.exists():
            return []
        with journals_file.open("rb") as f:
            return pickle.load(f)

    def hydrate_adjusting_journals(self):
        adj_file = self.journals_path / "adjusting_journals.pkl"
        if not adj_file.exists():
            return []
        with adj_file.open("rb") as f:
            return pickle.load(f)

    def hydrate_statistics(self):
        stat_file = self.statistics_path / "stat_repo.pkl"
        if not stat_file.exists():
            return None
        with stat_file.open("rb") as f:
            return pickle.load(f)

    def hydrate_admin_facility(self):
        admin_facility_file = self.admin_facility_path / "settlement_admin_facility.pkl"
        if not admin_facility_file.exists():
            return None
        with admin_facility_file.open("rb") as f:
            return pickle.load(f)

    def hydrate_snapshot(self):
        snap_file = (
            self.snapshots_path
            / f"snapshot_{self.period_name}.pkl"
        )
        if not snap_file.exists():
            return None
        with snap_file.open("rb") as f:
            return pickle.load(f)

    # ------------------------------------------------------------------
    # Integrity check (optional but powerful)
    # ------------------------------------------------------------------
    def exists(self) -> bool:
        return self.base_path.exists()

    def sealed(self) -> bool:
        return (
            (self.journals_path / "journals.pkl").exists()
            and (self.statistics_path / "stat_repo.pkl").exists()
            and (self.admin_facility_path / "settlement_admin_facility.pkl").exists()
        )
