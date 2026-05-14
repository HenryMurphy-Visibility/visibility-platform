# ============================================================
# top_holdings.py
# ============================================================

EXCLUDED_FA = {
    "PriceGainInvestment",
    "UnrealPriceGL",
    "UnrealFXGL",
    "UnrealPriceGLOffset",
    "UnrealFXGLOffset",
    "MarketVal",
}


def build(state):
    """
    Top Holdings Shape

    Input:
        StructuredState

    Output:
        dict keyed by investment
    """

    aggregated = {}

    for key, row in state.balances.items():

        investment, location, ls, fa = key

        # --------------------------------------------
        # FILTER (SHAPE LEVEL — NOT ENGINE)
        # --------------------------------------------

        if fa in EXCLUDED_FA:
            continue

        # --------------------------------------------
        # INIT
        # --------------------------------------------

        if investment not in aggregated:
            aggregated[investment] = {
                "opening_qty": 0.0,
                "opening_local": 0.0,
                "opening_book": 0.0,
                "movement_qty": 0.0,
                "movement_local": 0.0,
                "movement_book": 0.0,
                "closing_qty": 0.0,
                "closing_local": 0.0,
                "closing_book": 0.0,
            }

        tgt = aggregated[investment]

        # --------------------------------------------
        # ACCUMULATE
        # --------------------------------------------

        tgt["opening_qty"] += row.get("opening_qty") or 0.0
        tgt["opening_local"] += row.get("opening_local") or 0.0
        tgt["opening_book"] += row.get("opening_book") or 0.0

        tgt["movement_qty"] += row.get("movement_qty") or 0.0
        tgt["movement_local"] += row.get("movement_local") or 0.0
        tgt["movement_book"] += row.get("movement_book") or 0.0

        tgt["closing_qty"] += row.get("closing_qty") or 0.0
        tgt["closing_local"] += row.get("closing_local") or 0.0
        tgt["closing_book"] += row.get("closing_book") or 0.0

    # --------------------------------------------
    # SORT (by closing_local)
    # --------------------------------------------

    sorted_rows = sorted(
        aggregated.items(),
        key=lambda x: x[1]["closing_local"],
        reverse=True,
    )

    return sorted_rows