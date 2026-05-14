from collections import defaultdict
from typing import Optional, Dict, Any
from datetime import datetime

ENGINE_TOLERANCE = 0.0001
EXCLUDED_FA = {#"MarketVal",
               "UnrealPriceGLOffset",
               "UnrealFXGLOffset",
               "UnrealPriceGL",
               "UnrealFXGL",}

# ============================================================
# materialize_box_state
# ============================================================

from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, Optional
from .structured_state import StructuredState


def materialize_box_state(
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

        bal["opening_qty"]   += row.get("quantity") or 0.0
        bal["opening_local"] += row.get("local") or 0.0
        bal["opening_book"]  += row.get("book") or 0.0

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

        qty   = je.quantity or 0.0
        local = je.local or 0.0
        book  = je.book or 0.0

        # Skip zero-impact JE lines
        if (
            abs(qty)   < ENGINE_TOLERANCE
            and abs(local) < ENGINE_TOLERANCE
            and abs(book)  < ENGINE_TOLERANCE
        ):
            continue

        key = (
            je.investment,
            je.location,
            je.ls,
            je.financial_account,
        )

        bal = balances[key]

        bal["movement_qty"]   += qty
        bal["movement_local"] += local
        bal["movement_book"]  += book

        # Preserve structured JE detail (not full object, per your design)
        # ------------------------------------------------------------
        # Preserve structured JE detail for reporting layer
        # ------------------------------------------------------------

        bal["je_lines"].append({
            "ibor_date": je.ibor_date,
            "tradedate": getattr(je, "tradedate", None),
            "settledate": getattr(je, "settledate", None),
            "kdbegin": getattr(je, "kdbegin", None),
            "kdend": getattr(je, "kdend", None),

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

        bal["closing_qty"]   += row.get("quantity") or 0.0
        bal["closing_local"] += row.get("local") or 0.0
        bal["closing_book"]  += row.get("book") or 0.0

    # ------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------

    failures = validate_invariants(balances)

    return StructuredState(
        balances=dict(balances),   # freeze defaultdict into normal dict
        validation_failures=failures,
    )

ENGINE_TOLERANCE = 0.0001
# Accounts excluded from invariant validation only
VALIDATION_EXCLUDED_FA = {"UnrealPriceGL", "UnrealFXGL"}
# ============================================================
# VALIDATE INVARIANTS
# ============================================================

TOLERANCE = 0.0001


def validate_invariants(balances):
    failures = []

    for key, bal in balances.items():

        # key = (investment, location, ls, financial_account)
        financial_account = key[3]

        # Skip validation-only exclusions
        if financial_account in VALIDATION_EXCLUDED_FA:
            continue

        diff_book = (
                bal["opening_book"]
                + bal["movement_book"]
                - bal["closing_book"]
        )

        diff_local = (
                bal["opening_local"]
                + bal["movement_local"]
                - bal["closing_local"]
        )

        diff_qty = (
                bal["opening_qty"]
                + bal["movement_qty"]
                - bal["closing_qty"]
        )

        if (
                abs(diff_book) > TOLERANCE
                or abs(diff_local) > TOLERANCE
                or abs(diff_qty) > TOLERANCE
        ):
            failures.append({
                "key": key,
                "diff_book": diff_book,
                "diff_local": diff_local,
                "diff_qty": diff_qty,
            })

    return failures

def compute_box_state(extracted):
    balances = materialize_box_state(
        extracted["prior_structural"],
        extracted["current_structural"],
        extracted["journal_entries"],
        extracted["prior_kd"],
        extracted["current_kd"],
        extracted["uber_filter"],
    )

    validate_invariants(balances)

    return balances


def passes_filter(obj, uber_filter):
    """
    Deterministic state-level filtering.

    Supports:
        - exact match
        - set membership

    Example:
        {"investment": "IBM"}
        {"financial_account": {"Cost", "UnrealPriceGL"}}
    """

    if not uber_filter:
        return True

    for field, expected in uber_filter.items():

        if isinstance(obj, dict):
            value = obj.get(field)
        else:
            value = getattr(obj, field, None)

        # Set membership
        if isinstance(expected, (set, list, tuple)):
            if value not in expected:
                return False
        else:
            if value != expected:
                return False

    return True
