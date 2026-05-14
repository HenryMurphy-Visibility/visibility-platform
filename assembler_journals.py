# ======================================================================
#  assembler_journals.py
# ======================================================================
"""
JOURNALS ASSEMBLER

Read-only assembler responsible for reconstructing journal history
from period output containers.

Rules:
- No execution
- No scheduling
- No mutation
- No inference
"""

from pathlib import Path
import pickle


class JournalsAssembler:

    def assemble(
        self,
        *,
        portfolio: str,
        calendar: str,
        period_names: list[str],
        mode=None,
        as_of=None,
    ):
        if not portfolio:
            raise ValueError("Assembler requires explicit portfolio")

        if not calendar:
            raise ValueError("Assembler requires explicit calendar")

        if not period_names:
            return []

        base_path = (
                Path("C:/Users/hjmne/PycharmProjects/chest/funds")
                / portfolio
                / calendar
                / "Periods"
        )

        combined = []

        for period_name in period_names:
            journals_dir = (
                    base_path
                    / period_name
                    / "Outputs"
                    / "Journals"
            )

            if not journals_dir.exists():
                continue

            for fname in sorted(journals_dir.iterdir()):
                if fname.suffix == ".pkl":
                    with fname.open("rb") as f:
                        combined.extend(pickle.load(f))

        return combined
