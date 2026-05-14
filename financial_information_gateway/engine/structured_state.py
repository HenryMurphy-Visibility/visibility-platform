# ============================================================
# structured_state.py
# Canonical reconciled state container
# ============================================================

from typing import Dict, Any, List, Tuple


class StructuredState:
    """
    Immutable container for reconciled balances
    and invariant validation results.
    """

    def __init__(
        self,
        balances: Dict[Tuple, Dict[str, Any]],
        validation_failures: List[Dict[str, Any]],
    ):
        self._balances = balances
        self._validation_failures = validation_failures or []

    @property
    def balances(self):
        return self._balances

    @property
    def validation_failures(self):
        return self._validation_failures

    @property
    def is_valid(self) -> bool:
        return len(self._validation_failures) == 0