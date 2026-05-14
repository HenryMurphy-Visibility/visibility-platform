# ============================================================
# shape_extraction.py
# ============================================================

from typing import Dict, Any


# ============================================================
# STRUCTURAL STATE EXTRACTION
# ============================================================

def extract_structural_state_from_space(
        space,
) -> Dict[tuple, Dict[str, Any]]:
    """
    Extract structural accounting state from a BookkeepingSpace.

    Returns:
        Dict keyed by:

            (
                investment,
                location,
                ls,
                financial_account
            )

        Values:
            {
                "investment": str,
                "location": str,
                "ls": str,
                "financial_account": str,
                "quantity": float,
                "local": float,
                "book": float,
            }
    """

    structural = {}

    # =========================================================
    # ASSET / LIABILITY EXTRACTION
    # =========================================================

    al_repo = getattr(space, "asset_liability_repository", None)

    if al_repo:

        for investment, subspace in al_repo.investment_positions.items():
            entries = subspace.entries

            for key, values in entries.items():

                (
                    portfolio,
                    investment,
                    lotid,
                    tax_date,
                    ls,
                    location,
                    financial_account,
                ) = key

                quantity, local, book, notional, oface = values

                struct_key = (
                    investment,
                    location,
                    ls,
                    financial_account,
                )

                if struct_key not in structural:
                    structural[struct_key] = {
                        "investment": investment,
                        "location": location,
                        "ls": ls,
                        "financial_account": financial_account,
                        "quantity": 0.0,
                        "local": 0.0,
                        "book": 0.0,
                    }

                structural[struct_key]["quantity"] += quantity or 0.0
                structural[struct_key]["local"] += local or 0.0
                structural[struct_key]["book"] += book or 0.0

    # =========================================================
    # REVENUE / EXPENSE EXTRACTION
    # =========================================================

    re_repo = getattr(space, "revenue_expense_repository", None)

    if re_repo:

        for investment, balance_space in re_repo.balance_spaces_library.items():

            entries = balance_space
            if hasattr(balance_space, "entries"):
                entries = balance_space.entries

            if not isinstance(entries, dict):
                continue

            for key, values in entries.items():

                if not isinstance(key, tuple) or len(key) < 7:
                    continue

                (
                    portfolio,
                    investment,
                    lotid,
                    tax_date,
                    ls,
                    location,
                    financial_account,
                ) = key

                quantity = 0.0
                local = 0.0
                book = 0.0

                if isinstance(values, (tuple, list)):
                    if len(values) > 0:
                        quantity = values[0] or 0.0
                    if len(values) > 1:
                        local = values[1] or 0.0
                    if len(values) > 2:
                        book = values[2] or 0.0

                elif isinstance(values, dict):
                    quantity = values.get("quantity", 0.0)
                    local = values.get("local", 0.0)
                    book = values.get("book", 0.0)

                struct_key = (
                    investment,
                    location,
                    ls,
                    financial_account,
                )

                if struct_key not in structural:
                    structural[struct_key] = {
                        "investment": investment,
                        "location": location,
                        "ls": ls,
                        "financial_account": financial_account,
                        "quantity": 0.0,
                        "local": 0.0,
                        "book": 0.0,
                    }

                structural[struct_key]["quantity"] += quantity
                structural[struct_key]["local"] += local
                structural[struct_key]["book"] += book

    return structural
